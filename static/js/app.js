const { createApp, ref, computed, watch, onMounted, onUnmounted } = Vue;

const socket = io();

createApp({
  setup() {
    const activeTab = ref("file");
    const files = ref([]);
    const messages = ref([]);
    const ipv4List = ref([]);
    const ipv6List = ref([]);
    const selectedIP = ref("");
    const newText = ref("");
    const selectedFiles = ref([]);
    const selectAll = ref(false);
    const uploading = ref(false);
    const uploadProgress = ref(0);
    const dragover = ref(false);
    const chunkProgress = ref(0);
    const uploadStatus = ref("");
    const isAuthenticated = ref(false);
    const loginPassword = ref("");
    const loginError = ref("");
    const isDark = ref(false);

    const dropZone = ref(null);
    const fileInput = ref(null);

    const currentUrl = computed(() => {
      if (!selectedIP.value) return "";
      const port = location.port ? `:${location.port}` : "";
      const ip = selectedIP.value;
      return ip.includes(":") ? `http://[${ip}]${port}` : `http://${ip}${port}`;
    });

    const currentUrlDisplay = computed(() => `当前地址: ${currentUrl.value}`);

    watch(selectAll, (val) => {
      if (val) {
        selectedFiles.value = files.value.map((f) => f.name);
      } else {
        selectedFiles.value = [];
      }
    });

    watch(
      selectedFiles,
      (val) => {
        selectAll.value =
          val.length === files.value.length && files.value.length > 0;
      },
      { deep: true }
    );

    const checkAuth = async () => {
      try {
        const res = await fetch("/api/check-auth");
        const data = await res.json();
        isAuthenticated.value = data.authenticated;
        if (isAuthenticated.value) {
          loadIPs();
          socket.emit("request_files");
          socket.emit("request_messages");
        }
      } catch (err) {
      }
    };

    const login = async () => {
      try {
        const res = await fetch("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: loginPassword.value }),
        });
        const data = await res.json();
        if (data.success) {
          isAuthenticated.value = true;
          loginError.value = "";
          loadIPs();
          socket.emit("request_files");
          socket.emit("request_messages");
        } else {
          loginError.value = "密码错误";
        }
      } catch (err) {
        loginError.value = "登录失败";
      }
    };

    const loadIPs = async () => {
      try {
        const ipRes = await fetch("/api/ips").then((r) => r.json());
        ipv4List.value = ipRes.ipv4_list || [];
        ipv6List.value = ipRes.ipv6_list || [];
        if (ipv4List.value.length) {
          selectedIP.value = ipv4List.value[0];
        } else if (ipv6List.value) {
          selectedIP.value = ipv6List.value[0];
        } else {
          selectedIP.value = "127.0.0.1";
        }
      } catch (err) {
      }
    };

    const updateQRCode = () => {
      const el = document.getElementById("qrcode");
      if (!el || !currentUrl.value) return;
      el.innerHTML = "";
      new QRCode(el, {
        text: currentUrl.value,
        width: 200,
        height: 200,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.M,
      });
    };

    const copyUrl = async () => {
      try {
        await navigator.clipboard.writeText(currentUrl.value);
        alert("链接已复制到剪贴板");
      } catch {
        alert("复制失败，请手动复制：\n" + currentUrl.value);
      }
    };

    const copyText = async (text, event) => {
      const btn = event.currentTarget;
      const originalText = btn.textContent;
      const originalBg = btn.style.backgroundColor;

      const updateButton = (txt, bg) => {
        btn.textContent = txt;
        btn.style.backgroundColor = bg;
        setTimeout(() => {
          btn.textContent = originalText;
          btn.style.backgroundColor = originalBg || "#3498db";
        }, 2000);
      };
      try {
        await navigator.clipboard.writeText(text);
        updateButton("已复制", "#27ae60");
        return;
      } catch (err) {
      }
      const textArea = document.createElement("textarea");
      textArea.value = text;
      textArea.style.position = "fixed";
      textArea.style.top = "-3999px";
      textArea.style.left = "-3999px";
      textArea.style.opacity = "0";
      textArea.style.pointerEvents = "none";
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();

      try {
        const successful = document.execCommand("copy");
        if (successful) {
          updateButton("已复制", "#27ae60");
        } else {
          throw new Error("execCommand 失败");
        }
      } catch (err) {
        alert("自动复制失败，请手动复制：\n\n" + text);
      } finally {
        document.body.removeChild(textArea);
      }
    };

    const sendText = async () => {
      if (!newText.value.trim()) return;
      try {
        const res = await fetch("/api/text", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: newText.value.trim() }),
        });
        if (res.ok) {
          newText.value = "";
        } else if (res.status === 401) {
          isAuthenticated.value = false;
        }
      } catch (err) {
        alert("网络错误");
      }
    };

    const deleteMessage = async (msg) => {
      if (!confirm("确定删除这条消息？")) return;
      try {
        const res = await fetch("/api/delete_message", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: msg.content, time: msg.time }),
        });
        if (res.status === 401) {
          isAuthenticated.value = false;
        }
      } catch (err) {
        alert("删除失败");
      }
    };

    const deleteFile = async (filename) => {
      if (!confirm(`确定删除文件 "${filename}"？`)) return;
      try {
        const res = await fetch("/api/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename }),
        });
        if (res.status === 401) {
          isAuthenticated.value = false;
        }
      } catch (err) {
        alert("删除失败");
      }
    };

    const handleDrop = (e) => {
      dragover.value = false;
      const dt = e.dataTransfer;
      if (dt.files && dt.files.length) uploadFilesChunked(dt.files);
    };

    const handleFileInputChange = (e) => {
      if (e.target.files && e.target.files.length) uploadFilesChunked(e.target.files);
    };

    const uploadFilesChunked = async (fileList) => {
      const fileArray = Array.from(fileList);
      uploadStatus.value = `正在上传 ${fileArray.length} 个文件...`;
      uploading.value = true;
      uploadProgress.value = 0;

      let completed = 0;
      for (const file of fileArray) {
        try {
          if (file.size <= 10 * 1024 * 1024) {
            await uploadSimple(file);
          } else {
            await uploadSingleFileChunked(file);
          }
        } catch (err) {
          alert(`上传失败: ${file.name}`);
        }
        completed++;
        uploadProgress.value = Math.round((completed / fileArray.length) * 100);
        uploadStatus.value = `已完成 ${completed}/${fileArray.length} 个文件`;
      }

      uploading.value = false;
      uploadProgress.value = 0;
      fileInput.value.value = "";
      setTimeout(() => { uploadStatus.value = ""; }, 2000);
    };

    const uploadSimple = async (file) => {
      uploadStatus.value = `正在上传: ${file.name}`;
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/upload/simple", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        throw new Error("上传失败");
      }
    };

    const uploadSingleFileChunked = async (file) => {
      const CHUNK_SIZE = 10 * 1024 * 1024;
      const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
      uploadStatus.value = `正在上传: ${file.name}`;

      try {
        const initRes = await fetch("/api/upload/init", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: file.name, totalChunks }),
        });
        if (!initRes.ok) throw new Error("初始化上传失败");
        const data = await initRes.json();
        const { sessionId } = data;

        let uploadedChunks = [];
        for (let i = 0; i < totalChunks; i++) {
          const start = i * CHUNK_SIZE;
          const end = Math.min(start + CHUNK_SIZE, file.size);
          const chunk = file.slice(start, end);

          const formData = new FormData();
          formData.append("sessionId", sessionId);
          formData.append("chunkIndex", i);
          formData.append("file", chunk, file.name);

          try {
            const chunkRes = await fetch("/api/upload/chunk", {
              method: "POST",
              body: formData,
            });
            if (!chunkRes.ok) throw new Error("上传分片失败");
            const chunkData = await chunkRes.json();
            uploadedChunks.push(chunkData.chunkIndex);
          } catch (err) {
            uploadStatus.value = `分片 ${i + 1} 上传失败，正在重试...`;
            await new Promise(r => setTimeout(r, 1000));
            i--;
            continue;
          }
        }

        const completeRes = await fetch("/api/upload/complete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sessionId, filename: file.name }),
        });
        if (!completeRes.ok) throw new Error("完成上传失败");
      } catch (err) {
        throw err;
      }
    };

    const batchDownload = () => {
      if (!selectedFiles.value.length) {
        alert("请至少选择一个文件");
        return;
      }

      const formData = new FormData();
      selectedFiles.value.forEach((name) => {
        formData.append("selected_files", name);
      });

      fetch("/download_selected", {
        method: "POST",
        body: formData,
      })
        .then((res) => {
          if (!res.ok) throw new Error("下载失败");
          return res.blob();
        })
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "selected_files.zip";
          a.click();
          URL.revokeObjectURL(url);
        })
        .catch((err) => {
          alert("批量下载失败：" + err.message);
        });
    };

    const toggleTheme = () => {
      isDark.value = !isDark.value;
      document.body.classList.toggle("dark-mode", isDark.value);
      localStorage.setItem("darkMode", isDark.value);
      updateQRCode();
    };

    socket.on("auth_required", () => {
      isAuthenticated.value = false;
    });

    socket.on("connected", () => {
      isAuthenticated.value = true;
      socket.emit("request_files");
      socket.emit("request_messages");
    });

    socket.on("file_list", (data) => {
      files.value = data.files;
    });

    socket.on("message_list", (data) => {
      messages.value = data.messages;
    });

    socket.on("new_message", (data) => {
      messages.value.unshift(data);
      while (messages.value.length > 100) messages.value.pop();
    });

    socket.on("message_deleted", (data) => {
      const idx = messages.value.findIndex(m => m.content === data.content && m.time === data.time);
      if (idx !== -1) messages.value.splice(idx, 1);
    });

    socket.on("file_uploaded", (data) => {
      const exists = files.value.find(f => f.name === data.name);
      if (!exists) {
        files.value.unshift(data);
      }
    });

    socket.on("file_deleted", (data) => {
      const idx = files.value.findIndex(f => f.name === data.filename);
      if (idx !== -1) files.value.splice(idx, 1);
      const selIdx = selectedFiles.value.indexOf(data.filename);
      if (selIdx !== -1) selectedFiles.value.splice(selIdx, 1);
    });

    onMounted(() => {
      isDark.value = localStorage.getItem("darkMode") === "true";
      document.body.classList.toggle("dark-mode", isDark.value);
      checkAuth();
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
      chunkProgress,
      uploadStatus,
      isAuthenticated,
      loginPassword,
      loginError,
      isDark,
      dropZone,
      fileInput,

      currentUrlDisplay,
      updateQRCode,
      copyUrl,
      copyText,
      sendText,
      deleteMessage,
      deleteFile,
      handleDrop,
      handleFileInputChange,
      batchDownload,
      toggleTheme,
      login,
    };
  },
}).mount("#app");
