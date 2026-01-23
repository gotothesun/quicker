import os
import socket
import zipfile
import io
import threading
import ipaddress
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file

# ================== 配置 ==================
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder='static')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

PORT = 5000

messages = []  # 全局存储文本消息（内存中，程序重启会丢失）

def format_size(size_bytes):
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024*1024*1024):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024*1024):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} B"

# 获取本机 IP（IPv4 + IPv6）
def get_all_ips():
    ipv4_list = []
    ipv6_list = []
    seen = set()

    try:
        hostname = socket.gethostname()
        addr_info = socket.getaddrinfo(hostname, None)
        for info in addr_info:
            family, _, _, _, sockaddr = info
            ip = sockaddr[0]
            if ip in seen: continue
            seen.add(ip)
            try:
                addr = ipaddress.ip_address(ip)
                if addr.is_loopback: continue
                if family == socket.AF_INET and addr.is_private:
                    ipv4_list.append(ip)
                elif family == socket.AF_INET6:
                    if '%' in ip:
                        ip = ip.split('%')[0]
                    ip_obj = ipaddress.ip_address(ip)
                    if ip_obj.is_global or ip.startswith(('240', '241', '242', '243')):
                        ipv6_list.append(ip)
                    elif ip_obj.is_private or ip.startswith('fd'):
                        ipv6_list.append(ip)
            except:
                continue
    except:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            fallback_v4 = s.getsockname()[0]
            if fallback_v4 not in seen and ipaddress.ip_address(fallback_v4).is_private:
                ipv4_list.append(fallback_v4)
    except:
        pass

    def sort_v4(ip):
        if ip.startswith('192.168'): return (0, ip)
        elif ip.startswith('10.'): return (1, ip)
        elif ip.startswith('172.'): return (2, ip)
        else: return (3, ip)

    ipv4_list = sorted(list(set(ipv4_list)), key=sort_v4)
    ipv6_list = sorted(list(set(ipv6_list)))

    return ipv4_list, ipv6_list

LOCAL_IPV4, LOCAL_IPV6 = get_all_ips()

# ================== 路由 ==================

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 文件上传（拖拽/选择文件仍然走这里）
        files = request.files.getlist('files')
        for file in files:
            if file and file.filename:
                filename = file.filename
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                counter = 1
                while os.path.exists(filepath):
                    name, ext = os.path.splitext(filename)
                    filename = f"{name}({counter}){ext}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    counter += 1
                file.save(filepath)
        return '', 204

    # GET请求返回前端页面
    return send_from_directory('static', 'index.html')


@app.route('/api/files')
def api_files():
    file_data = []
    upload_dir = app.config['UPLOAD_FOLDER']
    for f in os.listdir(upload_dir):
        filepath = os.path.join(upload_dir, f)
        if os.path.isfile(filepath):
            size_bytes = os.path.getsize(filepath)
            file_data.append({
                "name": f,
                "size": format_size(size_bytes),
                "mtime": os.path.getmtime(filepath)  # 用于前端排序
            })
    file_data.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify(file_data)


@app.route('/api/messages')
def api_messages():
    return jsonify(messages)


@app.route('/api/ips')
def api_ips():
    return jsonify({
        "ipv4_list": LOCAL_IPV4,
        "ipv6_list": LOCAL_IPV6
    })


@app.route('/api/text', methods=['POST'])
def api_text():
    try:
        data = request.get_json()
        content = (data or {}).get('content', '').strip()
        if content:
            messages.append({
                'content': content,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        return '', 204
    except:
        return jsonify({"error": "Invalid JSON"}), 400


@app.route('/uploads/<path:filename>')
def download_file(filename):
    upload_dir = Path(app.config['UPLOAD_FOLDER']).resolve()
    requested_path = (upload_dir / filename).resolve()
    if not requested_path.is_file() or not requested_path.parent.samefile(upload_dir):
        return "文件不存在或无权限", 403
    return send_file(requested_path, as_attachment=True)


@app.route('/download_selected', methods=['POST'])
def download_selected():
    selected = request.form.getlist('selected_files')
    if not selected:
        return "未选择文件", 400

    upload_dir = Path(app.config['UPLOAD_FOLDER']).resolve()
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename in selected:
            safe_path = (upload_dir / filename).resolve()
            if not safe_path.is_file() or not safe_path.parent.samefile(upload_dir):
                continue
            zf.write(str(safe_path), arcname=filename)
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='selected_files.zip'
    )


# ================== 启动 ==================
def run_dual_stack_server():
    import socket
    from werkzeug.serving import make_server
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except:
        sock.close()
        return False
    try:
        sock.bind(('::', PORT))
        sock.listen(5)
        server = make_server('::', PORT, app, threaded=True, socket=sock)
        server.serve_forever()
    except:
        sock.close()
        return False
    return True


def run_separate_servers():
    from werkzeug.serving import make_server
    def run_ipv4():
        server = make_server('0.0.0.0', PORT, app, threaded=True)
        server.serve_forever()
    def run_ipv6():
        server = make_server('::', PORT, app, threaded=True)
        server.serve_forever()
    t4 = threading.Thread(target=run_ipv4, daemon=True)
    t6 = threading.Thread(target=run_ipv6, daemon=True)
    t4.start()
    t6.start()


if __name__ == '__main__':
    print("\n文件快传服务启动中...\n")

    if not run_dual_stack_server():
        run_separate_servers()

    print("可用访问地址:")
    if LOCAL_IPV4:
        for ip in LOCAL_IPV4:
            print(f"  http://{ip}:{PORT}")
    if LOCAL_IPV6:
        for ip in LOCAL_IPV6:
            print(f"  http://[{ip}]:{PORT}")
    if not LOCAL_IPV4 and not LOCAL_IPV6:
        print(f"  http://127.0.0.1:{PORT}")
    print(f"\n文件保存目录: {os.path.abspath(UPLOAD_FOLDER)}\n")

    import webbrowser, time
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(f'http://127.0.0.1:{PORT}')), daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n服务已停止")