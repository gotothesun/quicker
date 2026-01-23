const { createApp, ref, computed, watch, onMounted } = Vue;

createApp({
  setup() {
    const activeTab     = ref('file');
    const files         = ref([]);
    const messages      = ref([]);
    const ipv4List      = ref([]);
    const ipv6List      = ref([]);
    const selectedIP    = ref('');
    const newText       = ref('');
    const selectedFiles = ref([]);
    const selectAll     = ref(false);
    const uploading     = ref(false);
    const uploadProgress = ref(0);
    const dragover      = ref(false);

    const dropZone      = ref(null);
    const fileInput     = ref(null);

    // 当前显示的URL
    const currentUrl = computed(() => {
      if (!selectedIP.value) return '';
      const port = location.port ? `:${location.port}` : '';
      const ip = selectedIP.value;
      return ip.includes(':')
        ? `http://[${ip}]${port}`
        : `http://${ip}${port}`;
    });

    const currentUrlDisplay = computed(() => `当前地址: ${currentUrl.value}`);

    // 全选逻辑
    watch(selectAll, (val) => {
      if (val) {
        selectedFiles.value = files.value.map(f => f.name);
      } else {
        selectedFiles.value = [];
      }
    });

    watch(selectedFiles, (val) => {
      selectAll.value = val.length === files.value.length && files.value.length > 0;
    }, { deep: true });

    // 获取所有数据
    const loadData = async () => {
      try {
        const [filesRes, msgRes, ipRes] = await Promise.all([
          fetch('/api/files').then(r => r.json()),
          fetch('/api/messages').then(r => r.json()),
          fetch('/api/ips').then(r => r.json()),
        ]);

        files.value = filesRes;
        messages.value = msgRes;

        ipv4List.value = ipRes.ipv4_list || [];
        ipv6List.value = ipRes.ipv6_list || [];

        // 优先选第一个IPv4，没有则选IPv6，没有则本地
        if (ipv4List.value.length) {
          selectedIP.value = ipv4List.value[0];
        } else if (ipv6List.value.length) {
          selectedIP.value = ipv6List.value[0];
        } else {
          selectedIP.value = '127.0.0.1';
        }

      } catch (err) {
        console.error('加载数据失败', err);
      }
    };

    const updateQRCode = () => {
      const el = document.getElementById('qrcode');
      if (!el || !currentUrl.value) return;
      el.innerHTML = '';
      new QRCode(el, {
        text: currentUrl.value,
        width: 200,
        height: 200,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.M
      });
    };

    const copyUrl = async () => {
      try {
        await navigator.clipboard.writeText(currentUrl.value);
        alert('链接已复制到剪贴板');
      } catch {
        alert('复制失败，请手动复制：\n' + currentUrl.value);
      }
    };

    const copyText = async (text, event) => {
      const btn = event.currentTarget;  // 获取点击的按钮元素
      const originalText = btn.textContent;
      const originalBg = btn.style.backgroundColor;

      const updateButton = (txt, bg) => {
        btn.textContent = txt;
        btn.style.backgroundColor = bg;
        setTimeout(() => {
          btn.textContent = originalText;
          btn.style.backgroundColor = originalBg || '#3498db';
        }, 2000);
      };
      try {
        // 优先使用现代 Clipboard API
        await navigator.clipboard.writeText(text);
        updateButton('已复制', '#27ae60');
      } catch (err) {
        // fallback: 创建临时 textarea
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.top = '-3999px';
        textArea.style.left = '-3999px';
        textArea.style.opacity = '0';
        textArea.style.pointerEvents = 'none';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();

        try {
          const successful = document.execCommand('copy');
          if (successful) {
            updateButton('已复制', '#27ae60');
          } else {
            throw new Error('execCommand 失败');
          }
        } catch (fallbackErr) {
          console.error('Fallback 复制失败:', fallbackErr);
          alert('自动复制失败，请手动复制：\n\n' + text);
        } finally {
          document.body.removeChild(textArea);
        }
      }
    };

    const sendText = async () => {
      if (!newText.value.trim()) return;
      try {
        const res = await fetch('/api/text', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: newText.value.trim() })
        });
        if (res.ok) {
          newText.value = '';
          await loadData();  // 刷新消息列表
        } else {
          alert('发送失败');
        }
      } catch (err) {
        alert('网络错误');
      }
    };

    const handleDrop = (e) => {
      dragover.value = false;
      const dt = e.dataTransfer;
      if (dt.files && dt.files.length) uploadFiles(dt.files);
    };

    const handleFileInputChange = (e) => {
      if (e.target.files && e.target.files.length) uploadFiles(e.target.files);
    };

    const uploadFiles = (fileList) => {
      if (!fileList.length) return;
      uploading.value = true;
      uploadProgress.value = 0;

      const formData = new FormData();
      for (const file of fileList) {
        formData.append('files', file);
      }

      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/', true);

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          uploadProgress.value = Math.round((event.loaded / event.total) * 100);
        }
      };

      xhr.onload = () => {
        uploading.value = false;
        uploadProgress.value = 0;
        if (xhr.status === 200 || xhr.status === 204) {
          loadData();           // 刷新文件列表
          fileInput.value.value = ''; // 清空input
        } else {
          alert('上传失败：' + xhr.status);
        }
      };

      xhr.onerror = () => {
        uploading.value = false;
        alert('上传出错');
      };

      xhr.send(formData);
    };

    const batchDownload = () => {
      if (!selectedFiles.value.length) {
        alert('请至少选择一个文件');
        return;
      }

      const formData = new FormData();
      selectedFiles.value.forEach(name => {
        formData.append('selected_files', name);
      });

      fetch('/download_selected', {
        method: 'POST',
        body: formData
      })
      .then(res => {
        if (!res.ok) throw new Error('下载失败');
        return res.blob();
      })
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'selected_files.zip';
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch(err => {
        alert('批量下载失败：' + err.message);
      });
    };

    onMounted(() => {
      loadData();
      watch(selectedIP, updateQRCode);
      watch(currentUrl, updateQRCode);
    });

    return {
      activeTab,
      files,
      messages,
      ipv4List,
      ipv6List,
      selectedIP,
      newText,
      selectedFiles,
      selectAll,
      uploading,
      uploadProgress,
      dragover,
      dropZone,
      fileInput,

      currentUrlDisplay,
      updateQRCode,
      copyUrl,
      copyText,
      sendText,
      handleDrop,
      handleFileInputChange,
      batchDownload,
    };
  }
}).mount('#app');