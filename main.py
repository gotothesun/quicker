import os
import socket
import zipfile
import io
import threading
import json
import ipaddress
import time
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, send_file, session
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "uploads"
TEMP_FOLDER = "uploads/temp"
DATABASE_FILE = "data.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("QUICKER_SECRET", "quicker-secret-key-2024")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024 * 1024

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

CHUNK_SIZE = 10 * 1024 * 1024
PASSWORD = os.environ.get("QUICKER_PASSWORD", "admin123")


def init_database():
    import sqlite3
    import glob

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS upload_sessions")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_sessions (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            total_chunks INTEGER NOT NULL,
            uploaded_chunks TEXT NOT NULL,
            file_hash TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    for temp_file in glob.glob(os.path.join(TEMP_FOLDER, "*")):
        try:
            os.remove(temp_file)
        except Exception:
            pass


init_database()


def format_size(size_bytes):
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} B"


def safe_path_check(upload_dir, requested_filename):
    requested_path = os.path.join(upload_dir, requested_filename)
    requested_path = os.path.abspath(requested_path)
    upload_dir = os.path.abspath(upload_dir)
    if not requested_path.startswith(upload_dir):
        return False
    return os.path.isfile(requested_path)


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
            if ip in seen:
                continue
            seen.add(ip)
            try:
                addr = ipaddress.ip_address(ip)
                if addr.is_loopback:
                    continue
                if family == socket.AF_INET and addr.is_private:
                    ipv4_list.append(ip)
                elif family == socket.AF_INET6:
                    if "%" in ip:
                        ip = ip.split("%")[0]
                    ip_obj = ipaddress.ip_address(ip)
                    if ip_obj.is_global or ip.startswith(("240", "241", "242", "243")):
                        ipv6_list.append(ip)
                    elif ip_obj.is_private or ip.startswith("fd"):
                        ipv6_list.append(ip)
            except Exception:
                continue
    except Exception:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            fallback_v4 = s.getsockname()[0]
            if fallback_v4 not in seen and ipaddress.ip_address(fallback_v4).is_private:
                ipv4_list.append(fallback_v4)
    except Exception:
        pass

    def sort_v4(ip):
        if ip.startswith("192.168"):
            return (0, ip)
        elif ip.startswith("10."):
            return (1, ip)
        elif ip.startswith("172."):
            return (2, ip)
        else:
            return (3, ip)

    ipv4_list = sorted(list(set(ipv4_list)), key=sort_v4)
    ipv6_list = sorted(list(set(ipv6_list)))

    return ipv4_list, ipv6_list


LOCAL_IPV4, LOCAL_IPV6 = get_all_ips()


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/upload/simple", methods=["POST"])
def upload_simple():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    try:
        file = request.files.get("file")
        if not file or not file.filename:
            return jsonify({"error": "no file"}), 400

        filename = secure_filename(os.path.basename(file.filename))
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        counter = 1
        while os.path.exists(filepath):
            name, ext = os.path.splitext(filename)
            filename = f"{name}({counter}){ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            counter += 1

        file.save(filepath)
        size_bytes = os.path.getsize(filepath)
        socketio.emit(
            "file_uploaded",
            {
                "name": filename,
                "size": format_size(size_bytes),
                "size_bytes": size_bytes,
            },
        )
        return jsonify({"success": True, "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    if data.get("password") == PASSWORD:
        session["authenticated"] = True
        return jsonify({"success": True})
    return jsonify({"success": False}), 401


@app.route("/api/check-auth")
def check_auth():
    return jsonify({"authenticated": session.get("authenticated", False)})


@app.route("/api/files", methods=["GET"])
def api_files():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    file_data = []
    upload_dir = app.config["UPLOAD_FOLDER"]
    for f in os.listdir(upload_dir):
        filepath = os.path.join(upload_dir, f)
        if os.path.isfile(filepath) and not f.endswith(".tmp"):
            size_bytes = os.path.getsize(filepath)
            file_data.append(
                {
                    "name": f,
                    "size": format_size(size_bytes),
                    "size_bytes": size_bytes,
                    "mtime": os.path.getmtime(filepath),
                }
            )
    file_data.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify(file_data)


@app.route("/api/messages", methods=["GET"])
def api_messages():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    import sqlite3

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT content, time FROM messages ORDER BY id DESC LIMIT 100")
    messages = [{"content": row[0], "time": row[1]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(messages)


@app.route("/api/ips")
def api_ips():
    return jsonify({"ipv4_list": LOCAL_IPV4, "ipv6_list": LOCAL_IPV6})


@app.route("/api/text", methods=["POST"])
def api_text():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    try:
        data = request.get_json()
        content = (data or {}).get("content", "").strip()
        if content:
            import sqlite3

            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO messages (content, time, created_at) VALUES (?, ?, ?)",
                (content, now, now),
            )
            conn.commit()
            conn.close()
            socketio.emit("new_message", {"content": content, "time": now})
        return "", 204
    except Exception:
        return "", 204


@app.route("/api/upload/init", methods=["POST"])
def upload_init():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    try:
        data = request.get_json()
        filename = secure_filename(data.get("filename", ""))
        total_chunks = int(data.get("totalChunks", 1))
        if not filename or total_chunks <= 0:
            return jsonify({"error": "invalid parameters"}), 400
        import sqlite3

        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM upload_sessions WHERE created_at < ?",
            ((datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),),
        )
        conn.commit()
        session_id = f"{filename}_{int(time.time())}"
        temp_file = os.path.join(TEMP_FOLDER, session_id)
        cursor.execute(
            "INSERT INTO upload_sessions (id, filename, total_chunks, uploaded_chunks, file_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, filename, total_chunks, "[]", "", datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        return jsonify({"sessionId": session_id, "chunkSize": CHUNK_SIZE})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/chunk", methods=["POST"])
def upload_chunk():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    try:
        session_id = request.form.get("sessionId")
        chunk_index = int(request.form.get("chunkIndex", 0))
        file = request.files.get("file")
        if not session_id or not file:
            return jsonify({"error": "incomplete parameters"}), 400
        temp_file = os.path.join(TEMP_FOLDER, session_id)
        with open(temp_file, "ab") as f:
            f.seek(chunk_index * CHUNK_SIZE)
            f.write(file.read())
        import sqlite3

        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM upload_sessions WHERE id = ?", (session_id,))
        cursor.execute(
            "SELECT uploaded_chunks FROM upload_sessions WHERE id = ?", (session_id,)
        )
        row = cursor.fetchone()
        if row:
            uploaded = json.loads(row[0])
            if chunk_index not in uploaded:
                uploaded.append(chunk_index)
            cursor.execute(
                "UPDATE upload_sessions SET uploaded_chunks = ? WHERE id = ?",
                (json.dumps(uploaded), session_id),
            )
            conn.commit()
        conn.close()
        return jsonify({"success": True, "chunkIndex": chunk_index})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/complete", methods=["POST"])
def upload_complete():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    try:
        data = request.get_json()
        session_id = data.get("sessionId")
        filename = data.get("filename")
        if not session_id or not filename:
            return jsonify({"error": "incomplete parameters"}), 400
        import sqlite3

        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT total_chunks, uploaded_chunks FROM upload_sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "session not found"}), 404
        total_chunks = row[0]
        uploaded = json.loads(row[1])
        if len(uploaded) < total_chunks:
            conn.close()
            return jsonify(
                {
                    "error": "incomplete chunks",
                    "uploaded": len(uploaded),
                    "total": total_chunks,
                }
            ), 400
        temp_file = os.path.join(TEMP_FOLDER, session_id)
        final_path = os.path.join(UPLOAD_FOLDER, filename)
        counter = 1
        while os.path.exists(final_path):
            name, ext = os.path.splitext(filename)
            filename = f"{name}({counter}){ext}"
            final_path = os.path.join(UPLOAD_FOLDER, filename)
            counter += 1
        os.rename(temp_file, final_path)
        cursor.execute("DELETE FROM upload_sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()
        size_bytes = os.path.getsize(final_path)
        socketio.emit(
            "file_uploaded",
            {
                "name": filename,
                "size": format_size(size_bytes),
                "size_bytes": size_bytes,
            },
        )
        return jsonify({"success": True, "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/retry", methods=["POST"])
def upload_retry():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    try:
        data = request.get_json()
        session_id = data.get("sessionId")
        if not session_id:
            return jsonify({"error": "incomplete parameters"}), 400
        import sqlite3

        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT total_chunks, uploaded_chunks FROM upload_sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "session not found"}), 404
        total_chunks = row[0]
        uploaded = json.loads(row[1])
        missing_chunks = [i for i in range(total_chunks) if i not in uploaded]
        conn.close()
        return jsonify({"missingChunks": missing_chunks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete", methods=["POST"])
def delete_file():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    try:
        data = request.get_json()
        filename = data.get("filename")
        if not filename:
            return jsonify({"error": "filename cannot be empty"}), 400
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            socketio.emit("file_deleted", {"filename": filename})
            return jsonify({"success": True})
        return jsonify({"error": "file not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete_message", methods=["POST"])
def delete_message():
    if not session.get("authenticated"):
        return jsonify({"error": "unauthorized"}), 401
    try:
        data = request.get_json()
        content = data.get("content")
        time_str = data.get("time")
        import sqlite3

        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM messages WHERE content = ? AND time = ?", (content, time_str)
        )
        conn.commit()
        conn.close()
        socketio.emit("message_deleted", {"content": content, "time": time_str})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/uploads/<path:filename>")
def download_file(filename):
    if not session.get("authenticated"):
        return "unauthorized", 401
    upload_dir = Path(app.config["UPLOAD_FOLDER"]).resolve()
    if not safe_path_check(upload_dir, filename):
        return "file not found or permission denied", 403
    return send_file(str(upload_dir / filename), as_attachment=True)


@app.route("/download_selected", methods=["POST"])
def download_selected():
    if not session.get("authenticated"):
        return "unauthorized", 401
    selected = request.form.getlist("selected_files")
    if not selected:
        return "no file selected", 400

    upload_dir = Path(app.config["UPLOAD_FOLDER"]).resolve()
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in selected:
            if not safe_path_check(upload_dir, filename):
                continue
            zf.write(str(upload_dir / filename), arcname=filename)
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name="selected_files.zip",
    )


@socketio.on("connect")
def handle_connect():
    if session.get("authenticated"):
        emit("connected", {"status": "ok"})
    else:
        emit("auth_required")


@socketio.on("request_files")
def handle_request_files():
    if not session.get("authenticated"):
        emit("auth_error", {"message": "unauthorized"})
        return
    file_data = []
    upload_dir = app.config["UPLOAD_FOLDER"]
    for f in os.listdir(upload_dir):
        filepath = os.path.join(upload_dir, f)
        if os.path.isfile(filepath) and not f.endswith(".tmp"):
            size_bytes = os.path.getsize(filepath)
            file_data.append(
                {
                    "name": f,
                    "size": format_size(size_bytes),
                    "size_bytes": size_bytes,
                    "mtime": os.path.getmtime(filepath),
                }
            )
    file_data.sort(key=lambda x: x["mtime"], reverse=True)
    emit("file_list", {"files": file_data})


@socketio.on("request_messages")
def handle_request_messages():
    if not session.get("authenticated"):
        emit("auth_error", {"message": "unauthorized"})
        return
    import sqlite3

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT content, time FROM messages ORDER BY id DESC LIMIT 100")
    messages = [{"content": row[0], "time": row[1]} for row in cursor.fetchall()]
    conn.close()
    emit("message_list", {"messages": messages})


if __name__ == "__main__":
    print("\n文件快传服务启动中...\n")
    print("可用访问地址:")
    if LOCAL_IPV4:
        for ip in LOCAL_IPV4:
            print(f"  http://{ip}:5000")
    if LOCAL_IPV6:
        for ip in LOCAL_IPV6:
            print(f"  http://[{ip}]:5000")
    if not LOCAL_IPV4 and not LOCAL_IPV6:
        print(f"  http://127.0.0.1:5000")
    print(f"\n文件保存目录: {os.path.abspath(UPLOAD_FOLDER)}")
    print(f"默认密码: {PASSWORD}")
    import webbrowser

    threading.Thread(
        target=lambda: (time.sleep(1.5), webbrowser.open(f"http://127.0.0.1:5000")),
        daemon=True,
    ).start()
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)
