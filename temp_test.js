
        const API_BASE = "";
        let clusterSocket = null;

        function initClusterWebSocket() {
            try {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/cluster`;
                clusterSocket = new WebSocket(wsUrl);

                clusterSocket.onopen = function() {
                    console.log("⚡ Zero-latency WebSocket connected for Multi-Node Cluster.");
                };

                clusterSocket.onmessage = function(event) {
                    try {
                        const payload = JSON.parse(event.data);
                        if (payload.type === "cluster_status" && payload.data) {
                            updateClusterBadgeUI(payload.data);
                        }
                    } catch (e) {}
                };

                clusterSocket.onclose = function() {
                    setTimeout(initClusterWebSocket, 4000);
                };
            } catch (err) {
                console.error("WebSocket init error:", err);
            }
        }

        function updateClusterBadgeUI(clusterData) {
            const badge = document.getElementById("activeAgents");
            if (badge) {
                badge.innerText = `${clusterData.active_nodes || 1}/${clusterData.total_nodes || 1}`;
            }

            const tabBadge = document.getElementById("clusterNodeCountBadge");
            if (tabBadge) {
                tabBadge.innerText = `${clusterData.active_nodes || 1} Active`;
            }

            const totalEl = document.getElementById("statTotalNodes");
            const activeEl = document.getElementById("statActiveNodes");
            const modelsEl = document.getElementById("statAggModels");
            const clusterVramEl = document.getElementById("statClusterVRAM");

            if (totalEl) totalEl.innerText = clusterData.total_nodes || 1;
            if (activeEl) activeEl.innerText = clusterData.active_nodes || 1;
            if (modelsEl) modelsEl.innerText = (clusterData.aggregate_models || []).length;
            
            let totalClusterVramGB = 0;
            if (clusterData.nodes) {
                clusterData.nodes.forEach(n => {
                    totalClusterVramGB += (n.vram_used_gb || 0);
                });
            }
            if (clusterVramEl) clusterVramEl.innerText = `${totalClusterVramGB.toFixed(2)} GB`;

            const listEl = document.getElementById("clusterNodesList");
            if (listEl && clusterData.nodes) {
                listEl.innerHTML = clusterData.nodes.map(node => {
                    const statusColor = node.active ? "#10b981" : "#ef4444";
                    const statusBadge = node.active ? "ONLINE" : "UNREACHABLE";
                    const modelsPills = (node.models || []).map(m => `<span class="chip" style="font-size: 0.72rem; padding: 0.15rem 0.45rem;">${m}</span>`).join(" ");

                    const vramUsedGB = node.vram_used_gb || 0;
                    const loadedModels = node.loaded_models || [];
                    const loadedSummary = loadedModels.length > 0 
                        ? loadedModels.map(lm => `<b>${lm.name}</b> (${lm.size_vram_gb} GB VRAM)`).join(", ")
                        : "No model loaded in memory (Idle)";

                    return `
                        <div style="background: rgba(9, 13, 22, 0.6); border: 1px solid var(--panel-border); border-radius: 12px; padding: 1rem; display: flex; flex-direction: column; gap: 0.6rem;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="display: flex; align-items: center; gap: 0.5rem;">
                                    <span style="font-size: 1.1rem;">💻</span>
                                    <strong style="color: var(--text-main); font-size: 0.95rem;">${node.name}</strong>
                                    <span style="font-size: 0.75rem; color: var(--text-muted);">(${node.url})</span>
                                    <span style="font-size: 0.7rem; background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); padding: 0.1rem 0.4rem; border-radius: 10px;">${node.discovered_via || 'manual'}</span>
                                </div>
                                <div style="display: flex; align-items: center; gap: 0.6rem;">
                                    <span style="font-size: 0.75rem; color: var(--text-muted);">${node.latency_ms}ms</span>
                                    <span style="font-size: 0.72rem; padding: 0.15rem 0.5rem; border-radius: 12px; background: rgba(16, 185, 129, 0.15); color: ${statusColor}; font-weight: 600; text-transform: uppercase;">${statusBadge}</span>
                                </div>
                            </div>

                            <!-- Live Memory & VRAM Utilization Gauge -->
                            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 8px; padding: 0.6rem 0.8rem; display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <div style="font-size: 0.78rem; color: #38bdf8; font-weight: 600;">⚡ Active Model VRAM / Memory: <span style="color: var(--text-main); font-size: 0.85rem;">${vramUsedGB.toFixed(2)} GB</span></div>
                                    <div style="font-size: 0.74rem; color: var(--text-muted); margin-top: 0.15rem;">Active: ${loadedSummary}</div>
                                </div>
                                <div style="text-align: right;">
                                    <span style="font-size: 0.72rem; background: ${vramUsedGB > 0 ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255,255,255,0.05)'}; color: ${vramUsedGB > 0 ? '#38bdf8' : 'var(--text-muted)'}; padding: 0.15rem 0.5rem; border-radius: 10px; font-weight: 600;">
                                        ${vramUsedGB > 0 ? 'RAM/VRAM ACTIVE' : 'STANDBY'}
                                    </span>
                                </div>
                            </div>

                            <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.1rem;">
                                <strong>Installed Models (${node.models_count}):</strong>
                                <div style="display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.3rem;">
                                    ${modelsPills || '<span style="color: var(--text-muted);">No models detected</span>'}
                                </div>
                            </div>
                        </div>
                    `;
                }).join("");
            }
        }

        async function refreshClusterTabUI() {
            try {
                const res = await fetch(`${API_BASE}/api/cluster/nodes`);
                const data = await res.json();
                updateClusterBadgeUI(data);
            } catch (err) {
                console.error("Failed to refresh cluster nodes:", err);
            }
        }

        async function addClusterNodeFromUI() {
            const input = document.getElementById("addNodeUrlInput");
            if (!input || !input.value.trim()) return;
            const url = input.value.trim();
            try {
                const res = await fetch(`${API_BASE}/api/cluster/nodes/add`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ host_url: url })
                });
                const data = await res.json();
                alert(data.message || "Node added successfully!");
                input.value = "";
                refreshClusterTabUI();
            } catch (err) {
                alert("Failed to add node: " + err.message);
            }
        }

        initClusterWebSocket();

        async function fetchInstalledModels() {
            try {
                const res = await fetch(`${API_BASE}/api/models/installed`);
                const data = await res.json();
                if (data.models && data.models.length > 0) {
                    const chatSelect = document.getElementById("chatModelSelect");
                    if (chatSelect) {
                        const prev = chatSelect.value;
                        chatSelect.innerHTML = data.models.map(m => {
                            const isVision = m.includes("vl") || m.includes("vision") || m.includes("gemma3") || m.includes("moondream");
                            const badge = isVision ? " [👁️ Vision]" : "";
                            return `<option value="${m}">${m}${badge}</option>`;
                        }).join("");
                        if (data.models.includes(prev)) chatSelect.value = prev;
                        updateModelLabel(chatSelect.value);
                    }
                    const goalSelect = document.getElementById("goalModelSelect");
                    if (goalSelect) {
                        const prev = goalSelect.value;
                        goalSelect.innerHTML = data.models.map(m => `<option value="${m}">${m}</option>`).join("");
                        if (data.models.includes(prev)) goalSelect.value = prev;
                    }
                }
            } catch (err) {
                console.error("Error fetching installed models:", err);
            }
        }

        function openTab(tabName) {
            console.log("Switching to tab:", tabName);
            // Remove active from all buttons & panes
            const buttons = document.querySelectorAll('.tab-btn');
            buttons.forEach(btn => {
                if (btn.getAttribute('data-tab') === tabName) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });

            const panes = document.querySelectorAll('.tab-pane');
            panes.forEach(pane => {
                if (pane.id === `tab-${tabName}`) {
                    pane.classList.add('active');
                } else {
                    pane.classList.remove('active');
                }
            });

            if (tabName === 'goals') fetchGoals();
            if (tabName === 'reflections') fetchReflections();
            if (tabName === 'hfmodels') fetchTrendingHFModels();
            if (tabName === 'files') fetchWorkspaceFiles();
            if (tabName === 'media') { checkMediaStatus(); fetchMediaGallery(); }
        }

        // ── Media Studio Functions ──────────────────────────────────────────
        let currentForgeMode = 'txt2img';
        let activeGalleryMedia = [];

        function setForgeMode(mode) {
            currentForgeMode = mode;
            const btnTxt = document.getElementById('btnModeTxt2Img');
            const btnImg = document.getElementById('btnModeImg2Img');
            const section = document.getElementById('forgeImg2ImgSection');
            if (mode === 'img2img') {
                if (btnImg) btnImg.classList.add('active');
                if (btnTxt) btnTxt.classList.remove('active');
                if (section) section.style.display = 'block';
            } else {
                if (btnTxt) btnTxt.classList.add('active');
                if (btnImg) btnImg.classList.remove('active');
                if (section) section.style.display = 'none';
            }
        }

        async function handleForgeImgUpload(event) {
            const files = event.target.files;
            if (!files || files.length === 0) return;
            const formData = new FormData();
            formData.append("file", files[0]);
            try {
                const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: formData });
                const data = await res.json();
                if (data.status === "success") {
                    document.getElementById("forgeImg2ImgPath").value = data.filepath;
                } else {
                    alert("Upload error: " + (data.detail || data.message));
                }
            } catch (err) {
                alert("Upload failed: " + err.message);
            }
        }

        async function checkMediaStatus() {
            const forgeUrl = document.getElementById('forgeApiUrlInput')?.value || "http://127.0.0.1:7860";
            const comfyUrl = document.getElementById('comfyApiUrlInput')?.value || "http://127.0.0.1:8000";
            
            const badgeForge = document.getElementById('forgeStatusBadge');
            const badgeComfy = document.getElementById('comfyStatusBadge');

            if (badgeForge) {
                badgeForge.innerText = "TESTING...";
                badgeForge.style.background = "rgba(148, 163, 184, 0.2)";
                badgeForge.style.color = "#94a3b8";
            }
            if (badgeComfy) {
                badgeComfy.innerText = "TESTING...";
                badgeComfy.style.background = "rgba(148, 163, 184, 0.2)";
                badgeComfy.style.color = "#94a3b8";
            }

            try {
                const res = await fetch(`${API_BASE}/api/media/status?forge_url=${encodeURIComponent(forgeUrl)}&comfy_url=${encodeURIComponent(comfyUrl)}`);
                const data = await res.json();

                if (badgeForge) {
                    if (data.forge && data.forge.online) {
                        badgeForge.innerText = "🟢 ONLINE";
                        badgeForge.style.background = "rgba(16, 185, 129, 0.2)";
                        badgeForge.style.color = "#10b981";
                    } else {
                        badgeForge.innerText = "🔴 OFFLINE";
                        badgeForge.style.background = "rgba(239, 68, 68, 0.2)";
                        badgeForge.style.color = "#ef4444";
                    }
                }

                if (badgeComfy) {
                    if (data.comfy && data.comfy.online) {
                        badgeComfy.innerText = "🟢 ONLINE";
                        badgeComfy.style.background = "rgba(16, 185, 129, 0.2)";
                        badgeComfy.style.color = "#10b981";
                    } else {
                        badgeComfy.innerText = "🔴 OFFLINE";
                        badgeComfy.style.background = "rgba(239, 68, 68, 0.2)";
                        badgeComfy.style.color = "#ef4444";
                    }
                }
            } catch (e) {
                if (badgeForge) badgeForge.innerText = "OFFLINE";
                if (badgeComfy) badgeComfy.innerText = "OFFLINE";
            }
        }

        async function generateMediaImage() {
            const btn = document.getElementById('btnGenerateForgeImage');
            const prompt = document.getElementById('forgePromptInput')?.value.trim();
            if (!prompt) return alert("Please enter an image prompt!");

            const negPrompt = document.getElementById('forgeNegPromptInput')?.value.trim() || "";
            const width = parseInt(document.getElementById('forgeWidthSelect')?.value || 1024, 10);
            const height = parseInt(document.getElementById('forgeHeightSelect')?.value || 1024, 10);
            const steps = parseInt(document.getElementById('forgeStepsInput')?.value || 5, 10);
            const cfg = parseFloat(document.getElementById('forgeCfgInput')?.value || 1.0);
            const apiUrl = document.getElementById('forgeApiUrlInput')?.value || "http://127.0.0.1:7860";

            btn.disabled = true;
            btn.innerText = "⏳ Generating with SD Forge...";

            try {
                let res, data;
                if (currentForgeMode === 'img2img') {
                    const imgPath = document.getElementById('forgeImg2ImgPath')?.value.trim();
                    if (!imgPath) {
                        btn.disabled = false;
                        btn.innerText = "🎨 Generate / Edit Image";
                        return alert("Please upload or provide an input image path for img2img!");
                    }
                    const denoising = parseFloat(document.getElementById('forgeDenoisingInput')?.value || 0.75);
                    res = await fetch(`${API_BASE}/api/media/edit-image`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            image_path: imgPath,
                            prompt,
                            negative_prompt: negPrompt,
                            denoising_strength: denoising,
                            steps,
                            api_url: apiUrl
                        })
                    });
                } else {
                    res = await fetch(`${API_BASE}/api/media/generate-image`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            prompt,
                            negative_prompt: negPrompt,
                            width,
                            height,
                            steps,
                            cfg_scale: cfg,
                            api_url: apiUrl
                        })
                    });
                }

                data = await res.json();
                if (data.status === "success" && data.url) {
                    const cont = document.getElementById('forgeResultContainer');
                    const img = document.getElementById('forgeResultImg');
                    const dl = document.getElementById('forgeResultDownload');
                    if (img) img.src = data.url;
                    if (dl) dl.href = data.url;
                    if (cont) cont.style.display = "block";
                    fetchMediaGallery();
                } else {
                    alert("SD Forge Generation Result:\n" + (data.message || JSON.stringify(data)));
                }
            } catch (err) {
                alert("Generation error: " + err.message);
            } finally {
                btn.disabled = false;
                btn.innerText = "🎨 Generate / Edit Image";
            }
        }

        async function generateMediaVideo() {
            const btn = document.getElementById('btnGenerateComfyVideo');
            const prompt = document.getElementById('comfyPromptInput')?.value.trim();
            if (!prompt) return alert("Please enter a video motion prompt!");

            const negPrompt = document.getElementById('comfyNegPromptInput')?.value.trim() || "";
            const width = parseInt(document.getElementById('comfyWidthSelect')?.value || 512, 10);
            const height = parseInt(document.getElementById('comfyHeightSelect')?.value || 512, 10);
            const frames = parseInt(document.getElementById('comfyFramesInput')?.value || 16, 10);
            const fps = parseInt(document.getElementById('comfyFpsInput')?.value || 8, 10);
            const apiUrl = document.getElementById('comfyApiUrlInput')?.value || "http://127.0.0.1:8000";

            btn.disabled = true;
            btn.innerText = "⏳ Rendering Video with ComfyUI...";

            try {
                const res = await fetch(`${API_BASE}/api/media/generate-video`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt, negative_prompt: negPrompt, width, height, frames, fps, api_url: apiUrl })
                });
                const data = await res.json();
                if (data.status === "success" && data.url) {
                    const cont = document.getElementById('comfyResultContainer');
                    const vid = document.getElementById('comfyResultVideo');
                    const dl = document.getElementById('comfyResultDownload');
                    if (vid) vid.src = data.url;
                    if (dl) dl.href = data.url;
                    if (cont) cont.style.display = "block";
                    fetchMediaGallery();
                } else {
                    alert("ComfyUI Video Result:\n" + (data.message || JSON.stringify(data)));
                }
            } catch (err) {
                alert("Video generation error: " + err.message);
            } finally {
                btn.disabled = false;
                btn.innerText = "🎬 Generate Video";
            }
        }

        async function fetchMediaGallery() {
            const grid = document.getElementById('mediaGalleryGrid');
            if (!grid) return;
            try {
                const res = await fetch(`${API_BASE}/api/media/gallery?media_type=all`);
                const data = await res.json();
                const all = [
                    ...(data.images || []).map(i => ({ ...i, mediaType: 'image' })),
                    ...(data.videos || []).map(v => ({ ...v, mediaType: 'video' }))
                ];
                all.sort((a,b) => (b.modified || '').localeCompare(a.modified || ''));
                activeGalleryMedia = all;
                renderGallery(activeGalleryMedia);
            } catch (err) {
                grid.innerHTML = `<div style="color: var(--accent-red);">Failed to load gallery.</div>`;
            }
        }

        function filterGallery(type) {
            ['All', 'Images', 'Videos'].forEach(k => {
                const btn = document.getElementById(`galleryFilter${k}`);
                if (btn) btn.classList.remove('active');
            });
            const activeBtn = document.getElementById(`galleryFilter${type.charAt(0).toUpperCase() + type.slice(1)}`);
            if (activeBtn) activeBtn.classList.add('active');

            if (type === 'all') {
                renderGallery(activeGalleryMedia);
            } else if (type === 'images') {
                renderGallery(activeGalleryMedia.filter(m => m.mediaType === 'image'));
            } else if (type === 'videos') {
                renderGallery(activeGalleryMedia.filter(m => m.mediaType === 'video'));
            }
        }

        function renderGallery(items) {
            const grid = document.getElementById('mediaGalleryGrid');
            if (!grid) return;
            if (!items || items.length === 0) {
                grid.innerHTML = `<div style="color: var(--text-muted); font-size: 0.88rem; padding: 1.5rem; text-align: center; grid-column: 1 / -1;">No images or videos generated yet in ~/ollama_workspace/. Create one above!</div>`;
                return;
            }
            grid.innerHTML = items.map(m => {
                const isVideo = m.mediaType === 'video';
                const mediaElement = isVideo
                    ? `<video src="${m.url}" controls muted loop style="width: 100%; height: 160px; object-fit: cover; border-radius: 8px;"></video>`
                    : `<img src="${m.url}" alt="${m.name}" style="width: 100%; height: 160px; object-fit: cover; border-radius: 8px; cursor: pointer;" onclick="window.open('${m.url}', '_blank')">`;
                
                return `
                    <div style="background: rgba(9, 13, 22, 0.6); border: 1px solid var(--panel-border); border-radius: 10px; padding: 0.6rem; display: flex; flex-direction: column; gap: 0.4rem;">
                        ${mediaElement}
                        <div style="font-size: 0.78rem; font-weight: 600; color: #c7d2fe; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${m.name}</div>
                        <div style="font-size: 0.72rem; color: var(--text-muted); display: flex; justify-content: space-between;">
                            <span>${m.size_formatted || ''}</span>
                            <span>${(m.modified || '').substring(0, 10)}</span>
                        </div>
                        <div style="display: flex; gap: 0.3rem; margin-top: 0.2rem;">
                            <a href="${m.url}" download target="_blank" class="chip" style="font-size: 0.72rem; padding: 0.15rem 0.5rem; text-decoration: none; text-align: center; flex: 1; background: rgba(16, 185, 129, 0.15); color: #10b981;">📥 Download</a>
                            <button class="chip" onclick="navigator.clipboard.writeText(window.location.origin + '${m.url}'); alert('Copied URL: ' + window.location.origin + '${m.url}');" style="font-size: 0.72rem; padding: 0.15rem 0.4rem;">📋</button>
                        </div>
                    </div>
                `;
            }).join("");
        }

        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    const tabName = btn.getAttribute('data-tab');
                    openTab(tabName);
                });
            });

            fetchInstalledModels();
            loadSessionsList();
            fetchChatHistory(currentSessionId);
            fetchWorkspaceFiles();
        });

        // ── Voice Input (Speech-to-Text with Continuous Listening) ───────────────────
        let activeRecognition = null;
        let isUserListeningRequested = false;

        function toggleVoiceInput(targetInputId, btnId) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRecognition) {
                alert("Speech recognition is not supported on this browser. Try Google Chrome, MS Edge, or Safari!");
                return;
            }

            const btn = document.getElementById(btnId);
            const input = document.getElementById(targetInputId);

            if (isUserListeningRequested) {
                // User wants to stop listening
                isUserListeningRequested = false;
                if (activeRecognition) {
                    try { activeRecognition.stop(); } catch(e) {}
                    activeRecognition = null;
                }
                if (btn) {
                    btn.style.background = "";
                    btn.innerText = btnId === "btnVoiceChat" ? "🎙️" : "🎙️ Dictate Goal";
                }
                return;
            }

            isUserListeningRequested = true;

            function startRecognitionSession() {
                if (!isUserListeningRequested) return;

                activeRecognition = new SpeechRecognition();
                activeRecognition.continuous = true;
                activeRecognition.interimResults = true;
                activeRecognition.lang = "en-US";

                if (btn) {
                    btn.style.background = "rgba(239, 68, 68, 0.3)";
                    btn.innerText = "🔴 Listening (Continuous)...";
                }

                activeRecognition.onresult = (event) => {
                    let transcript = "";
                    for (let i = 0; i < event.results.length; ++i) {
                        transcript += event.results[i][0].transcript;
                    }
                    if (input) {
                        input.value = transcript;
                    }
                };

                activeRecognition.onerror = (event) => {
                    console.warn("Speech recognition notice:", event.error);
                };

                activeRecognition.onend = () => {
                    // Auto-restart if user has not clicked stop
                    if (isUserListeningRequested) {
                        try {
                            activeRecognition.start();
                        } catch (e) {
                            setTimeout(startRecognitionSession, 300);
                        }
                    } else {
                        if (btn) {
                            btn.style.background = "";
                            btn.innerText = btnId === "btnVoiceChat" ? "🎙️" : "🎙️ Dictate Goal";
                        }
                        activeRecognition = null;
                    }
                };

                activeRecognition.start();
            }

            startRecognitionSession();
        }

        function updateModelLabel(val) {
            document.getElementById("chatModelBadge").innerText = "Model: " + val;
        }

        function handleKeyDown(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        }

        function sendSample(text) {
            document.getElementById("chatInput").value = text;
            sendMessage();
        }

        // ── Session Management State ─────────────────────────────────────────
        let currentSessionId = "default_session";
        let allWorkspaceFiles = [];

        async function loadSessionsList() {
            try {
                const res = await fetch(`${API_BASE}/api/chat/sessions`);
                const data = await res.json();
                const select = document.getElementById("chatSessionSelect");
                if (!select) return;

                const sessions = data.sessions || [];
                // Ensure default_session is always represented
                const hasDefault = sessions.some(s => s.session_id === "default_session");
                let optionsHtml = hasDefault ? "" : `<option value="default_session">Default Chat</option>`;
                
                sessions.forEach(s => {
                    const label = s.session_id === "default_session" 
                        ? `Default Chat (${s.message_count} msgs)` 
                        : `${s.title || s.session_id} (${s.message_count})`;
                    optionsHtml += `<option value="${s.session_id}">${label}</option>`;
                });

                select.innerHTML = optionsHtml;
                select.value = currentSessionId;
            } catch (err) {
                console.warn("Could not load sessions list:", err);
            }
        }

        async function switchSession(sessionId) {
            currentSessionId = sessionId;
            await fetchChatHistory(currentSessionId);
        }

        async function createNewSession() {
            const name = prompt("Enter a name or topic for the new chat session (or leave blank for auto):");
            const newId = name && name.trim() ? "session_" + name.trim().toLowerCase().replace(/[^a-z0-9]/g, "_") : "chat_" + Date.now();
            currentSessionId = newId;

            const select = document.getElementById("chatSessionSelect");
            if (select) {
                const opt = document.createElement("option");
                opt.value = newId;
                opt.innerText = (name && name.trim()) || "New Chat";
                select.appendChild(opt);
                select.value = newId;
            }

            document.getElementById("chatMessages").innerHTML = `
                <div class="message-row agent">
                    <div class="avatar agent">🤖</div>
                    <div class="bubble">
                        Started new conversation thread! How can I help you?
                    </div>
                </div>
            `;
        }

        async function deleteCurrentSession() {
            if (currentSessionId === "default_session") {
                if (!confirm("Clear message history in default session?")) return;
                await clearChat();
                return;
            }

            if (!confirm(`Delete chat session '${currentSessionId}'?`)) return;

            try {
                await fetch(`${API_BASE}/api/chat/sessions/${encodeURIComponent(currentSessionId)}`, { method: "DELETE" });
            } catch (err) {
                console.warn("Session deletion error:", err);
            }

            currentSessionId = "default_session";
            await loadSessionsList();
            await fetchChatHistory("default_session");
        }

        async function clearChat() {
            if (!confirm("Are you sure you want to clear this chat's messages?")) return;
            try {
                await fetch(`${API_BASE}/api/chat/clear?session_id=${encodeURIComponent(currentSessionId)}`, { method: "POST" });
            } catch (err) {
                console.warn("Failed to reset backend session history:", err);
            }
            document.getElementById("chatMessages").innerHTML = `
                <div class="message-row agent">
                    <div class="avatar agent">🤖</div>
                    <div class="bubble">
                        Chat cleared. How can I help you next?
                    </div>
                </div>
            `;
            loadSessionsList();
        }

        async function fetchChatHistory(sessionId = "default_session") {
            try {
                const res = await fetch(`${API_BASE}/api/chat/history?session_id=${encodeURIComponent(sessionId)}`);
                const data = await res.json();
                const container = document.getElementById("chatMessages");
                if (res.ok && data.messages && data.messages.length > 0) {
                    container.innerHTML = "";
                    let lastUsedModel = "";
                    data.messages.forEach(msg => {
                        appendMessage(msg.role, msg.content, msg.attachment, msg.model || "");
                        if (msg.model) lastUsedModel = msg.model;
                    });
                    // Auto-sync the model dropdown to this session's model
                    if (lastUsedModel) {
                        const modelSel = document.getElementById("chatModelSelect");
                        if (modelSel && Array.from(modelSel.options).some(o => o.value === lastUsedModel)) {
                            modelSel.value = lastUsedModel;
                        }
                        updateModelLabel(lastUsedModel);
                    }
                } else {
                    container.innerHTML = `
                        <div class="message-row agent">
                            <div class="avatar agent">🤖</div>
                            <div class="bubble">
                                Hello! I am your Level 4 Autonomous Agent. Ask me anything, or give me a complex task to analyze, research, or write code for. How can I help you today?
                            </div>
                        </div>
                    `;
                }
            } catch (err) {
                console.warn("Could not load chat history:", err);
            }
        }

        function appendMessage(role, content, fileAttachment = "", modelName = "") {
            const container = document.getElementById("chatMessages");
            const isUser = role === "user";
            const row = document.createElement("div");
            row.className = `message-row ${role}`;
            
            const avatarHtml = isUser ? `<div class="avatar user">👤</div>` : `<div class="avatar agent">🤖</div>`;
            
            let extraAttachmentHtml = "";
            if (fileAttachment) {
                const ext = fileAttachment.split('.').pop().toLowerCase();
                const isImg = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(ext);
                const fileUrl = `/workspace/${fileAttachment}`;
                if (isImg) {
                    extraAttachmentHtml = `
                        <div style="margin-top: 0.6rem; padding: 0.5rem; background: rgba(0,0,0,0.3); border-radius: 8px; border: 1px solid var(--panel-border);">
                            <div style="font-size: 0.78rem; color: #818cf8; margin-bottom: 0.4rem;">📷 Uploaded Input Image: <code>${fileAttachment}</code></div>
                            <img src="${fileUrl}" alt="Input image" style="max-width: 320px; max-height: 240px; border-radius: 8px; object-fit: contain; border: 1px solid rgba(255,255,255,0.1);" onclick="window.open('${fileUrl}', '_blank')">
                        </div>
                    `;
                } else {
                    extraAttachmentHtml = `
                        <div style="margin-top: 0.6rem; padding: 0.4rem 0.8rem; background: rgba(0,0,0,0.3); border-radius: 8px; border: 1px solid var(--panel-border); font-size: 0.82rem; color: #818cf8;">
                            📄 Attached File: <a href="${fileUrl}" target="_blank" style="color: #6366f1;">${fileAttachment}</a>
                        </div>
                    `;
                }
            }

            let modelBadgeHtml = "";
            if (role === "agent" && modelName) {
                modelBadgeHtml = `
                    <div style="font-size: 0.72rem; color: #818cf8; margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.35rem;">
                        <span style="background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.35); padding: 0.15rem 0.55rem; border-radius: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 0.25rem; color: #a5b4fc;">
                            🧠 <code>${modelName}</code>
                        </span>
                    </div>
                `;
            }

            let rawContent = (content || "").trim();

            // Fold reasoning thoughts (<think>...</think>) into a sleek accordion drawer
            let formattedContent = rawContent.replace(/<think>([\s\S]*?)<\/think>/gi, (match, thought) => {
                const trimmed = thought.trim();
                if (!trimmed) return "";
                return `<details style="margin-bottom: 0.6rem; background: rgba(9, 13, 22, 0.5); border: 1px solid rgba(129, 140, 248, 0.25); border-radius: 8px; padding: 0.4rem 0.75rem;"><summary style="cursor: pointer; color: #818cf8; font-weight: 600; font-size: 0.8rem;">💭 Thought Process (Click to view)</summary><div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.4rem; white-space: pre-wrap; font-family: inherit;">${trimmed}</div></details>`;
            });

            // Prevent blank agent bubbles
            if (!formattedContent.trim() && role === "agent") {
                formattedContent = "*(No response generated by model. Please retry or adjust prompt.)*";
            }

            // Convert markdown media (![alt](/workspace/...) and [alt](/workspace/images/...)) to <img> or <video> tags
            formattedContent = formattedContent
                .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, src) => {
                    const cleanSrc = src.trim();
                    if (cleanSrc.endsWith('.mp4') || cleanSrc.endsWith('.webm') || cleanSrc.endsWith('.mov')) {
                        return `<div style="margin-top: 0.6rem;"><video src="${cleanSrc}" controls autoplay loop muted style="max-width: 440px; max-height: 320px; border-radius: 10px; border: 1px solid var(--primary); box-shadow: 0 4px 14px var(--primary-glow);"></video></div>`;
                    }
                    return `<div style="margin-top: 0.6rem;"><img src="${cleanSrc}" alt="${alt}" style="max-width: 400px; max-height: 320px; border-radius: 10px; border: 1px solid var(--primary); box-shadow: 0 4px 14px var(--primary-glow);" onclick="window.open('${cleanSrc}', '_blank')"></div>`;
                })
                .replace(/`~\/ollama_workspace\/images\/([^`]+)`/g, (match, filename) => {
                    const src = `/workspace/images/${filename}`;
                    return `<code>~/ollama_workspace/images/${filename}</code><div style="margin-top: 0.6rem;"><img src="${src}" alt="Generated image" style="max-width: 400px; max-height: 320px; border-radius: 10px; border: 1px solid var(--primary); box-shadow: 0 4px 14px var(--primary-glow);" onclick="window.open('${src}', '_blank')"></div>`;
                })
                .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
                .replace(/\n/g, '<br>');

            // Automatic APK Download Button: Only display when APK was actually produced or requested
            let apkNoticeHtml = "";
            const isApkArtifact = rawContent.includes(".apk") && (
                rawContent.toLowerCase().includes("successfully compiled") || 
                rawContent.includes("Download URL: `/workspace/") || 
                rawContent.includes("Generated Android APK") ||
                rawContent.toLowerCase().includes("ready for direct installation")
            );

            if (isApkArtifact) {
                const apkMatch = rawContent.match(/([\w-]+\.apk)/i);
                const apkFilename = apkMatch ? apkMatch[1] : "app-debug.apk";
                apkNoticeHtml = `
                    <div style="margin-top: 0.8rem; padding: 0.6rem 0.9rem; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 10px; display: flex; align-items: center; justify-content: space-between;">
                        <span style="font-size: 0.85rem; color: #a7f3d0; font-weight: 600;">📱 Generated Android APK File: <code>${apkFilename}</code></span>
                        <a href="/workspace/${apkFilename}" download target="_blank" style="background: #10b981; color: white; padding: 0.4rem 0.9rem; border-radius: 6px; text-decoration: none; font-size: 0.82rem; font-weight: 600; display: inline-flex; align-items: center; gap: 0.3rem;">📥 Download APK</a>
                    </div>
                `;
            }

            row.innerHTML = `${avatarHtml}<div class="bubble">${modelBadgeHtml}${formattedContent}${extraAttachmentHtml}${apkNoticeHtml}</div>`;
            container.appendChild(row);
            container.scrollTop = container.scrollHeight;
        }

        async function sendMessage() {
            const input = document.getElementById("chatInput");
            const btn = document.getElementById("btnSend");
            let prompt = input.value.trim();
            const model = document.getElementById("chatModelSelect").value;

            if (!prompt && !activeUploadedFilePath) return;

            const attachedFile = activeUploadedFilePath;

            // If a file is attached and prompt doesn't mention it, automatically include the file reference!
            if (attachedFile && !prompt.includes(attachedFile)) {
                prompt = `[Attached File: ${attachedFile}] ${prompt}`;
            }

            // Clear upload preview pill after attaching
            clearFileUpload();

            // Render User Bubble with thumbnail if image attached
            appendMessage("user", prompt, attachedFile);
            input.value = "";
            btn.disabled = true;
            btn.innerHTML = "⏳ Thinking...";

            // Real-Time Tool & Reasoning Thinking Bubble
            const container = document.getElementById("chatMessages");
            const tempRow = document.createElement("div");
            tempRow.className = "message-row agent";
            tempRow.id = "thinkingBubble";
            tempRow.innerHTML = `<div class="avatar agent">🤖</div><div class="bubble" style="color: var(--text-muted);"><div style="font-size: 0.72rem; color: #818cf8; margin-bottom: 0.35rem;"><span style="background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.35); padding: 0.12rem 0.5rem; border-radius: 12px; font-weight: 600; color: #a5b4fc;">🧠 <code>${model}</code></span></div><span class="tool-status-text"><i>Agent is reasoning & executing tools...</i></span></div>`;
            container.appendChild(tempRow);
            container.scrollTop = container.scrollHeight;

            const maxTurnsEl = document.getElementById("chatMaxTurnsSelect");
            const max_turns = maxTurnsEl ? parseInt(maxTurnsEl.value, 10) : 50;

            let activeSessionId = currentSessionId || "default_session";

            try {
                // Connect via SSE streaming endpoint for live tool badges
                const res = await fetch(`${API_BASE}/api/chat/stream`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        prompt,
                        model,
                        max_turns,
                        session_id: activeSessionId,
                        attachment: attachedFile || ""
                    })
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    const tb = document.getElementById("thinkingBubble");
                    if (tb) tb.remove();
                    appendMessage("agent", "❌ Error (" + res.status + "): " + (errData.detail || JSON.stringify(errData)), "", model);
                    return;
                }

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";
                let finalResult = "";

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split("\n\n");
                    buffer = lines.pop(); // incomplete remainder

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (trimmed.startsWith("data: ")) {
                            try {
                                const evt = JSON.parse(trimmed.slice(6));
                                const tbStatus = document.querySelector("#thinkingBubble .tool-status-text");
                                
                                if (evt.type === "tool_start" && tbStatus) {
                                    tbStatus.innerHTML = `<span style="color: #38bdf8; font-weight: 600;">⚡ Executing Tool:</span> <code style="color: #a7f3d0; background: rgba(0,0,0,0.4); padding: 0.2rem 0.4rem; border-radius: 4px;">${evt.data.tool}</code> <span style="font-size: 0.78rem; color: var(--text-muted);">running...</span>`;
                                } else if (evt.type === "tool_end" && tbStatus) {
                                    tbStatus.innerHTML = `<span style="color: #10b981; font-weight: 600;">✓ Completed Tool:</span> <code style="color: #a7f3d0; background: rgba(0,0,0,0.4); padding: 0.2rem 0.4rem; border-radius: 4px;">${evt.data.tool}</code>`;
                                } else if (evt.type === "thought" && tbStatus) {
                                    const preview = evt.data.length > 75 ? evt.data.substring(0, 75) + "..." : evt.data;
                                    tbStatus.innerHTML = `<span style="color: #818cf8; font-weight: 600;">💭 Reasoning:</span> <span style="font-size: 0.8rem; color: var(--text-muted);">${preview}</span>`;
                                } else if (evt.type === "done") {
                                    finalResult = evt.result || "";
                                } else if (evt.type === "error") {
                                    finalResult = "❌ Error: " + (evt.error || evt.data || "Agent execution failed");
                                }
                            } catch (e) {
                                console.debug("SSE Parse skip:", e);
                            }
                        }
                    }
                }

                const tb = document.getElementById("thinkingBubble");
                if (tb) tb.remove();

                if (finalResult) {
                    appendMessage("agent", finalResult, "", model);
                } else {
                    appendMessage("agent", "*(Task execution finished)*", "", model);
                }

                loadSessionsList();
                fetchWorkspaceFiles();
            } catch (err) {
                // Fallback to standard POST in case SSE streaming is blocked
                try {
                    const fallbackRes = await fetch(`${API_BASE}/api/task/run`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ prompt, model, max_turns, session_id: activeSessionId, attachment: attachedFile || "" })
                    });
                    const tb = document.getElementById("thinkingBubble");
                    if (tb) tb.remove();
                    const fbData = await fallbackRes.json();
                    appendMessage("agent", fbData.result || "Execution completed.", "", model);
                    loadSessionsList();
                    fetchWorkspaceFiles();
                } catch (fallbackErr) {
                    const tb = document.getElementById("thinkingBubble");
                    if (tb) tb.remove();
                    appendMessage("agent", "❌ Network / Execution Error: " + err.message, "", model);
                }
            } finally {
                btn.disabled = false;
                btn.innerHTML = "<span>Send</span> ➔";
            }
        }

        // ── Workspace File Explorer & Artifact Viewer Functions ──────────────
        async function fetchWorkspaceFiles() {
            try {
                const res = await fetch(`${API_BASE}/api/workspace/files`);
                const data = await res.json();
                allWorkspaceFiles = data.files || [];
                renderWorkspaceFiles(allWorkspaceFiles);
            } catch (err) {
                console.warn("Error fetching workspace files:", err);
            }
        }

        let openFolders = new Set([""]); // Root is implicitly empty string, but we just use path prefixes

        function toggleFolder(path) {
            if (openFolders.has(path)) openFolders.delete(path);
            else openFolders.add(path);
            filterWorkspaceFiles();
        }

        function renderWorkspaceFiles(files) {
            const container = document.getElementById("workspaceFilesTreeBody");
            if (!container) return;

            if (!files || files.length === 0) {
                container.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--text-muted);">No files found in ~/ollama_workspace/</div>`;
                return;
            }

            const typeBadges = {
                "apk": `<span style="background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); padding: 0.15rem 0.5rem; border-radius: 6px; font-size: 0.7rem; font-weight: 600;">📱 APK</span>`,
                "image": `<span style="background: rgba(236, 72, 153, 0.2); color: #f472b6; border: 1px solid rgba(236, 72, 153, 0.4); padding: 0.15rem 0.5rem; border-radius: 6px; font-size: 0.7rem; font-weight: 600;">🖼️ Image</span>`,
                "video": `<span style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.4); padding: 0.15rem 0.5rem; border-radius: 6px; font-size: 0.7rem; font-weight: 600;">🎬 Video</span>`,
                "code": `<span style="background: rgba(99, 102, 241, 0.2); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.4); padding: 0.15rem 0.5rem; border-radius: 6px; font-size: 0.7rem; font-weight: 600;">💻 Code</span>`,
                "file": `<span style="background: rgba(148, 163, 184, 0.2); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.4); padding: 0.15rem 0.5rem; border-radius: 6px; font-size: 0.7rem; font-weight: 600;">📄 File</span>`
            };

            const root = {};
            files.forEach(f => {
                // Normalize slashes
                const parts = f.relative_path.replace(/\\/g, "/").split("/");
                let current = root;
                for (let i = 0; i < parts.length - 1; i++) {
                    if (!current[parts[i]]) current[parts[i]] = {};
                    current = current[parts[i]];
                }
                current[parts[parts.length - 1]] = f;
            });

            function buildTreeHtml(node, pathPrefix = "") {
                let html = "";
                const keys = Object.keys(node).sort((a, b) => {
                    const aIsFile = !!node[a].relative_path;
                    const bIsFile = !!node[b].relative_path;
                    if (aIsFile === bIsFile) return a.localeCompare(b);
                    return aIsFile ? 1 : -1;
                });

                keys.forEach(key => {
                    const item = node[key];
                    const currentPath = pathPrefix ? `${pathPrefix}/${key}` : key;

                    if (item.relative_path) {
                        // File Node
                        const badge = typeBadges[item.type] || typeBadges["file"];
                        const isPreviewable = item.type === "code" || ["txt", "md", "json", "xml", "py", "java", "gradle", "bat"].includes(item.extension);
                        const previewBtn = isPreviewable 
                            ? `<button class="chip" onclick="previewWorkspaceFile('${item.relative_path}')" style="padding: 0.2rem 0.5rem; font-size: 0.75rem; background: rgba(99, 102, 241, 0.15); color: #818cf8;">👁 Preview</button>` 
                            : "";

                        html += `
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.45rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.02);">
                                <div style="display: flex; align-items: center; gap: 0.6rem; color: #c7d2fe; font-size: 0.88rem; flex-wrap: wrap;">
                                    <span style="opacity: 0.7;">📄</span> 
                                    <span style="font-weight: 500;">${item.name}</span>
                                    ${badge}
                                    <span style="font-size: 0.75rem; color: var(--text-muted); margin-left: 0.2rem;">${item.size_formatted}</span>
                                    <span style="font-size: 0.75rem; color: var(--text-muted);">${item.modified}</span>
                                </div>
                                <div style="display: flex; gap: 0.4rem; align-items: center;">
                                    ${previewBtn}
                                    <a href="${item.download_url}" download target="_blank" class="chip" style="padding: 0.2rem 0.5rem; font-size: 0.75rem; background: rgba(16, 185, 129, 0.15); color: #10b981; text-decoration: none;">📥 Download</a>
                                    <button onclick="deleteWorkspaceFile('${item.relative_path}')" class="chip" style="padding: 0.2rem 0.5rem; font-size: 0.75rem; color: #ef4444; border-color: rgba(239, 68, 68, 0.3);">🗑</button>
                                </div>
                            </div>
                        `;
                    } else {
                        // Folder Node
                        // If there is an active search, folders are auto-expanded.
                        const isSearching = (document.getElementById("workspaceSearchInput").value || "").trim().length > 0;
                        const isOpen = isSearching || openFolders.has(currentPath);
                        const displayStyle = isOpen ? "block" : "none";
                        const icon = isOpen ? "📂" : "📁";

                        html += `
                            <div style="margin-top: 0.2rem;">
                                <div onclick="toggleFolder('${currentPath}')" style="cursor: pointer; display: flex; align-items: center; gap: 0.5rem; color: #a5b4fc; font-weight: 600; padding: 0.4rem 1rem; user-select: none; border-bottom: 1px solid rgba(255,255,255,0.02); background: rgba(0,0,0,0.1);">
                                    <span>${icon}</span> ${key}/
                                </div>
                                <div style="display: ${displayStyle}; border-left: 1px solid rgba(99, 102, 241, 0.2); margin-left: 1.25rem;">
                                    ${buildTreeHtml(item, currentPath)}
                                </div>
                            </div>
                        `;
                    }
                });
                return html;
            }

            container.innerHTML = buildTreeHtml(root);
        }

        function filterWorkspaceFiles() {
            const query = (document.getElementById("workspaceSearchInput").value || "").toLowerCase().trim();
            if (!query) {
                renderWorkspaceFiles(allWorkspaceFiles);
                return;
            }
            const filtered = allWorkspaceFiles.filter(f => 
                f.name.toLowerCase().includes(query) || 
                f.relative_path.toLowerCase().includes(query) ||
                f.extension.toLowerCase().includes(query)
            );
            renderWorkspaceFiles(filtered);
        }

        async function previewWorkspaceFile(relPath) {
            try {
                const res = await fetch(`${API_BASE}/api/workspace/file?path=${encodeURIComponent(relPath)}`);
                const data = await res.json();
                document.getElementById("previewModalTitle").innerText = `File Preview: ${relPath}`;
                document.getElementById("previewModalContent").innerText = data.content || "(No text content)";
                document.getElementById("filePreviewModal").style.display = "flex";
            } catch (err) {
                alert("Could not load preview: " + err.message);
            }
        }

        function closePreviewModal() {
            document.getElementById("filePreviewModal").style.display = "none";
        }

        async function deleteWorkspaceFile(relPath) {
            if (!confirm(`Delete '${relPath}' from workspace?`)) return;
            try {
                await fetch(`${API_BASE}/api/workspace/file?path=${encodeURIComponent(relPath)}`, { method: "DELETE" });
                await fetchWorkspaceFiles();
            } catch (err) {
                alert("Failed to delete file: " + err.message);
            }
        }

        let activeGoalUploadedFilePath = "";

        async function handleGoalFileUpload(event) {
            const files = event.target.files;
            if (!files || files.length === 0) return;
            const file = files[0];

            const formData = new FormData();
            formData.append("file", file);

            const uploadBtn = document.getElementById("btnUploadGoalFile");
            uploadBtn.innerHTML = "⏳ Uploading...";
            uploadBtn.disabled = true;

            try {
                const res = await fetch(`${API_BASE}/api/upload`, {
                    method: "POST",
                    body: formData
                });
                const data = await res.json();
                if (res.ok && data.status === "success") {
                    activeGoalUploadedFilePath = data.filepath;
                    document.getElementById("goalFileUploadInfo").innerText = `📄 Attached: ${data.filepath} (${(data.size / 1024).toFixed(1)} KB)`;
                    document.getElementById("goalFileUploadPreview").style.display = "flex";

                    const goalPrompt = document.getElementById("goalPrompt");
                    if (!goalPrompt.value.trim()) {
                        goalPrompt.value = `Analyze and execute long-horizon goal for uploaded file ${data.filepath}: `;
                    }
                } else {
                    alert("Upload failed: " + (data.detail || data.message || "Unknown error"));
                }
            } catch (err) {
                alert("Upload error: " + err.message);
            } finally {
                uploadBtn.innerHTML = "📁 Upload File";
                uploadBtn.disabled = false;
                event.target.value = "";
            }
        }

        function clearGoalFileUpload() {
            activeGoalUploadedFilePath = "";
            document.getElementById("goalFileUploadPreview").style.display = "none";
        }

        async function createGoal() {
            const promptInput = document.getElementById("goalPrompt");
            let prompt = promptInput.value.trim();
            const modelSelect = document.getElementById("goalModelSelect");
            const model = modelSelect ? modelSelect.value : "deepseek-r1:8b";
            if (!prompt && !activeGoalUploadedFilePath) return alert("Enter a goal prompt or upload a file!");

            const attachedGoalFile = activeGoalUploadedFilePath;

            // Prepend file attachment if not present in prompt text
            if (attachedGoalFile && !prompt.includes(attachedGoalFile)) {
                prompt = `[Attached File: ${attachedGoalFile}] ${prompt}`;
            }

            clearGoalFileUpload();

            const createBtn = document.querySelector("#tab-goals .panel .btn-send");
            const origText = createBtn ? createBtn.innerHTML : "+ Decompose & Register Goal";
            if (createBtn) {
                createBtn.disabled = true;
                createBtn.innerHTML = "⏳ Decomposing with LLM...";
            }

            try {
                const res = await fetch(`${API_BASE}/api/goals/create`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt, model })
                });
                const data = await res.json();
                if (res.ok && data.status === "success") {
                    promptInput.value = "";
                    fetchGoals();
                    alert(`✓ Goal created successfully with ${data.tasks.length} sub-tasks!`);
                } else {
                    alert("Failed to create goal: " + (data.detail || JSON.stringify(data)));
                }
            } catch (err) {
                alert("Error creating goal: " + err.message);
            } finally {
                if (createBtn) {
                    createBtn.disabled = false;
                    createBtn.innerHTML = origText;
                }
            }
        }

        const collapsedGoals = {};

        function toggleGoalCollapse(goalId) {
            collapsedGoals[goalId] = !collapsedGoals[goalId];
            fetchGoals();
        }

        async function deleteGoal(goalId, goalTitle) {
            if (!confirm(`Are you sure you want to permanently delete goal "${goalTitle}"? This cannot be undone.`)) return;
            try {
                const res = await fetch(`${API_BASE}/api/goals/${goalId}`, { method: "DELETE" });
                const data = await res.json();
                alert(data.message || "Goal deleted successfully.");
                fetchGoals();
            } catch (err) {
                alert("Failed to delete goal: " + err.message);
            }
        }

        async function fetchGoals() {
            const list = document.getElementById("goalsList");
            // Preserve existing scroll positions of outer container, inner subtask containers, and summary boxes
            const scrollPositions = {};
            if (list) {
                scrollPositions["_main_list"] = list.scrollTop;
                list.querySelectorAll('[data-subtask-container]').forEach(el => {
                    scrollPositions[el.getAttribute('data-subtask-container')] = el.scrollTop;
                });
                list.querySelectorAll('[data-summary-container]').forEach(el => {
                    scrollPositions[el.getAttribute('data-summary-container')] = el.scrollTop;
                });
            }

            try {
                const res = await fetch(`${API_BASE}/api/goals`);
                const goals = await res.json();

                if (goals.length === 0) {
                    list.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">No active goals found. Create one on the left!</div>`;
                    return;
                }

                list.innerHTML = goals.map(g => {
                    const isRunning = g.tasks && g.tasks.some(t => t.status === "in_progress");
                    const isCollapsed = !!collapsedGoals[g.goal_id];
                    const btnText = isRunning ? "⏳ Running..." : "▶ Run Next Task";
                    const btnDisabled = isRunning ? "disabled" : "";
                    
                    const tasksListHtml = (g.tasks || []).map((t, idx) => {
                        let badgeColor = "#94a3b8";
                        let badgeBg = "rgba(255,255,255,0.05)";
                        let icon = "⚪";
                        if (t.status === "completed") { badgeColor = "#10b981"; badgeBg = "rgba(16, 185, 129, 0.15)"; icon = "✅"; }
                        else if (t.status === "in_progress") { badgeColor = "#f59e0b"; badgeBg = "rgba(245, 158, 11, 0.15)"; icon = "⏳"; }
                        else if (t.status === "failed") { badgeColor = "#ef4444"; badgeBg = "rgba(239, 68, 68, 0.15)"; icon = "❌"; }

                        const outputText = t.output || t.result || "";
                        let resultPreview = "";
                        let taskApkDownload = "";

                        if (outputText.includes(".apk")) {
                            const apkMatch = outputText.match(/([\w-]+\.apk)/i);
                            const apkFilename = apkMatch ? apkMatch[1] : "HelloWorld-debug.apk";
                            taskApkDownload = `
                                <div style="margin-top: 0.4rem; padding: 0.4rem 0.6rem; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 6px; display: flex; align-items: center; justify-content: space-between;">
                                    <span style="font-size: 0.8rem; color: #a7f3d0; font-weight: 600;">📱 Generated APK: <code>${apkFilename}</code></span>
                                    <a href="/workspace/${apkFilename}" download target="_blank" style="background: #10b981; color: white; padding: 0.25rem 0.6rem; border-radius: 4px; text-decoration: none; font-size: 0.75rem; font-weight: 600;">📥 Download APK</a>
                                </div>
                            `;
                        }

                        if (outputText) {
                            resultPreview = `<div style="font-size: 0.8rem; color: #a7f3d0; background: #060911; padding: 0.5rem 0.7rem; border-radius: 6px; margin-top: 0.4rem; font-family: 'JetBrains Mono', monospace; white-space: pre-wrap; max-height: 180px; overflow-y: auto; border: 1px solid rgba(16, 185, 129, 0.2);">${outputText}</div>${taskApkDownload}`;
                        } else if (t.status === "in_progress") {
                            resultPreview = `<div style="font-size: 0.78rem; color: #fde68a; margin-top: 0.2rem; font-style: italic;">Agent is actively executing this sub-task...</div>`;
                        }

                        return `
                            <div style="background: rgba(17, 24, 39, 0.5); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 0.6rem 0.8rem; margin-top: 0.4rem;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="font-size: 0.88rem; color: var(--text-main); font-weight: 500;">
                                        ${icon} Session ${idx+1}: ${t.description || t.title}
                                    </span>
                                    <span style="font-size: 0.72rem; padding: 0.15rem 0.5rem; border-radius: 12px; background: ${badgeBg}; color: ${badgeColor}; font-weight: 600; text-transform: uppercase;">
                                        ${t.status}
                                    </span>
                                </div>
                                ${resultPreview}
                            </div>
                        `;
                    }).join("");

                    return `
                    <div style="background: rgba(9, 13, 22, 0.6); border: 1px solid var(--panel-border); border-radius: 12px; padding: 1rem; display: flex; flex-direction: column; gap: 0.6rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="display: flex; align-items: center; gap: 0.5rem; flex: 1;">
                                <button onclick="toggleGoalCollapse('${g.goal_id}')" style="background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.9rem;">
                                    ${isCollapsed ? '▶' : '▼'}
                                </button>
                                <strong style="color: var(--text-main); font-size: 1rem;">${g.title}</strong>
                            </div>
                            <div style="display: flex; align-items: center; gap: 0.6rem;">
                                <span style="color: var(--accent-green); font-weight: 600;">${g.progress_pct.toFixed(0)}%</span>
                                <button class="chip" onclick="deleteGoal('${g.goal_id}', '${g.title.replace(/'/g, "\\'")}')" style="color: #ef4444; border-color: rgba(239, 68, 68, 0.3); padding: 0.2rem 0.5rem; font-size: 0.75rem;" title="Delete Goal">🗑️ Delete</button>
                            </div>
                        </div>
                        
                        <div style="background: rgba(255, 255, 255, 0.06); border-radius: 8px; height: 8px; width: 100%; overflow: hidden;">
                            <div style="background: linear-gradient(90deg, var(--primary), var(--accent-green)); height: 100%; width: ${g.progress_pct}%"></div>
                        </div>
                        
                        <!-- Overall Goal Final Synthesis -->
                        ${g.final_summary ? `
                        <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; padding: 0.8rem 1rem; margin-top: 0.3rem;">
                            <div style="font-weight: 600; color: #a7f3d0; font-size: 0.9rem; margin-bottom: 0.3rem; display: flex; align-items: center; justify-content: space-between;">
                                <span>🎯 Overall Goal Final Synthesis</span>
                                ${g.final_summary.includes(".apk") ? `
                                    <a href="/workspace/${(g.final_summary.match(/([\w-]+\.apk)/i) || ['', 'NearbyShare-debug.apk'])[1]}" download target="_blank" style="background: #10b981; color: white; padding: 0.25rem 0.6rem; border-radius: 4px; text-decoration: none; font-size: 0.75rem; font-weight: 600;">📥 Download APK</a>
                                ` : ''}
                            </div>
                            <div data-summary-container="summary_${g.goal_id}" style="font-size: 0.85rem; color: var(--text-main); line-height: 1.5; white-space: pre-wrap; max-height: 200px; overflow-y: auto;">${g.final_summary}</div>
                        </div>
                        ` : ''}

                        <!-- Sub-tasks Breakdown List (Collapsible) -->
                        <div style="margin-top: 0.3rem; display: ${isCollapsed ? 'none' : 'block'};">
                            <div style="font-size: 0.8rem; color: var(--text-muted); font-weight: 600; margin-bottom: 0.2rem;">Sub-task Breakdown (${g.tasks_count} Sessions):</div>
                            <div data-subtask-container="${g.goal_id}" style="max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 0.2rem;">
                                ${tasksListHtml}
                            </div>

                            <!-- Interactive Follow-Up Question Input with File Attachment -->
                            <div style="margin-top: 0.6rem; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(99, 102, 241, 0.2); border-radius: 8px; padding: 0.6rem;">
                                <div style="font-size: 0.78rem; color: #818cf8; font-weight: 600; margin-bottom: 0.4rem; display: flex; align-items: center; justify-content: space-between;">
                                    <span>💬 Ask Follow-up Question on this Goal:</span>
                                    <div style="display: flex; gap: 0.3rem; align-items: center;">
                                        ${(g.title.toLowerCase().includes("apk") || (g.final_summary && g.final_summary.toLowerCase().includes(".apk"))) ? `
                                            <a href="/workspace/NearbyShare-debug.apk" download target="_blank" style="background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); text-decoration: none; padding: 0.15rem 0.45rem; border-radius: 12px; font-size: 0.72rem; display: inline-flex; align-items: center; gap: 0.2rem;">📱 Download APK</a>
                                        ` : ''}
                                        <button class="chip" onclick="document.getElementById('followup_file_${g.goal_id}').click()" style="font-size: 0.72rem; padding: 0.15rem 0.45rem;">📁 Attach File</button>
                                        <button class="chip" onclick="fetchWorkspaceFiles()" style="font-size: 0.72rem; padding: 0.15rem 0.45rem;">📂 Browse App Files</button>
                                    </div>
                                </div>
                                <input type="file" id="followup_file_${g.goal_id}" style="display: none;" onchange="handleFollowupFileUpload(event, '${g.goal_id}')">
                                <div id="followup_file_preview_${g.goal_id}" style="display: none; font-size: 0.75rem; color: #818cf8; margin-bottom: 0.4rem; background: rgba(0,0,0,0.3); padding: 0.2rem 0.5rem; border-radius: 4px;"></div>
                                <div style="display: flex; gap: 0.4rem;">
                                    <input type="text" id="followup_input_${g.goal_id}" placeholder="Ask follow-up (e.g. 'Where is the app code file?', 'Add dark mode')..." style="flex: 1; background: rgba(0,0,0,0.4); border: 1px solid var(--panel-border); border-radius: 6px; padding: 0.4rem 0.6rem; color: white; font-size: 0.85rem;" onkeydown="if(event.key==='Enter') sendFollowup('${g.goal_id}')">
                                    <button class="btn-send" onclick="sendFollowup('${g.goal_id}')" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;">💬 Ask</button>
                                </div>
                            </div>
                        </div>

                        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 0.6rem;">
                            <span style="font-size: 0.8rem; color: var(--text-muted);">Model: ${g.model}</span>
                            <div style="display: flex; gap: 0.4rem;">
                                <button class="btn-send" onclick="runGoalTask('${g.goal_id}')" ${btnDisabled} style="padding: 0.3rem 0.7rem; font-size: 0.8rem; ${isRunning ? 'opacity: 0.6; cursor: not-allowed;' : ''}">${btnText}</button>
                                ${isRunning ? `<button class="chip" onclick="killGoal('${g.goal_id}')" style="color: #ef4444; border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.15); padding: 0.3rem 0.6rem; font-size: 0.8rem;">🛑 Kill</button>` : ''}
                            </div>
                        </div>
                    </div>
                `}).join("");

                // Restore saved scroll positions
                if (scrollPositions["_main_list"] !== undefined) {
                    list.scrollTop = scrollPositions["_main_list"];
                }
                list.querySelectorAll('[data-subtask-container]').forEach(el => {
                    const gid = el.getAttribute('data-subtask-container');
                    if (scrollPositions[gid] !== undefined) {
                        el.scrollTop = scrollPositions[gid];
                    }
                });
                list.querySelectorAll('[data-summary-container]').forEach(el => {
                    const sid = el.getAttribute('data-summary-container');
                    if (scrollPositions[sid] !== undefined) {
                        el.scrollTop = scrollPositions[sid];
                    }
                });
                return goals;
            } catch (err) {
                list.innerHTML = `<div style="color: var(--accent-red);">Failed to load goals.</div>`;
                return [];
            }
        }

        async function killGoal(goalId) {
            if (!confirm("Are you sure you want to stop and kill active execution for this goal?")) return;
            try {
                if (window.goalPollTimer) {
                    clearInterval(window.goalPollTimer);
                    window.goalPollTimer = null;
                }
                const res = await fetch(`${API_BASE}/api/goals/${goalId}/kill`, { method: "POST" });
                const data = await res.json();
                alert(data.message || "Goal execution killed successfully.");
                fetchGoals();
            } catch (err) {
                alert("Error stopping goal execution: " + err.message);
            }
        }

        async function emergencyKillAll() {
            if (!confirm("🛑 EMERGENCY KILL SWITCH: Are you sure you want to terminate ALL running processes and reset in-progress task states?")) return;
            try {
                if (window.goalPollTimer) {
                    clearInterval(window.goalPollTimer);
                    window.goalPollTimer = null;
                }
                const res = await fetch(`${API_BASE}/api/tasks/kill-all`, { method: "POST" });
                const data = await res.json();
                alert("🛑 " + (data.message || "All running tasks and processes terminated safely."));
                fetchGoals();
            } catch (err) {
                alert("Error triggering emergency kill: " + err.message);
            }
        }

        async function runGoalTask(goalId) {
            try {
                await fetch(`${API_BASE}/api/goals/${goalId}/run?auto_continue=true`, { method: "POST" });
                await fetchGoals();
                
                // Clear any existing polling timer
                if (window.goalPollTimer) {
                    clearInterval(window.goalPollTimer);
                    window.goalPollTimer = null;
                }

                // Poll every 3 seconds only while goals are running
                window.goalPollTimer = setInterval(async () => {
                    const goals = await fetchGoals();
                    const isAnyTaskRunning = goals && Array.isArray(goals) && goals.some(g => 
                        g.tasks && g.tasks.some(t => t.status === "in_progress")
                    );
                    if (!isAnyTaskRunning) {
                        console.log("All tasks completed. Stopping background polling timer.");
                        clearInterval(window.goalPollTimer);
                        window.goalPollTimer = null;
                    }
                }, 3000);
            } catch (err) {
                alert("Failed to run task: " + err.message);
            }
        }

        const activeFollowupFiles = {};

        async function handleFollowupFileUpload(event, goalId) {
            const files = event.target.files;
            if (!files || files.length === 0) return;
            const file = files[0];
            const formData = new FormData();
            formData.append("file", file);

            const preview = document.getElementById(`followup_file_preview_${goalId}`);
            if (preview) {
                preview.style.display = "block";
                preview.innerText = "⏳ Uploading file...";
            }

            try {
                const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: formData });
                const data = await res.json();
                if (res.ok && data.status === "success") {
                    activeFollowupFiles[goalId] = data.filepath;
                    if (preview) {
                        preview.innerText = `📄 Attached: ${data.filepath} (${(data.size / 1024).toFixed(1)} KB)`;
                    }
                } else {
                    alert("Upload failed: " + (data.detail || data.message));
                }
            } catch (err) {
                alert("Upload error: " + err.message);
            } finally {
                event.target.value = "";
            }
        }

        async function sendFollowup(goalId) {
            const input = document.getElementById(`followup_input_${goalId}`);
            if (!input) return;
            let prompt = input.value.trim();
            const attachedFile = activeFollowupFiles[goalId] || "";

            if (!prompt && !attachedFile) return alert("Please enter a follow-up question or attach a file!");

            if (attachedFile && !prompt.includes(attachedFile)) {
                prompt = `[Attached File: ${attachedFile}] ${prompt}`;
            }

            // Clear attached file state
            delete activeFollowupFiles[goalId];
            const preview = document.getElementById(`followup_file_preview_${goalId}`);
            if (preview) preview.style.display = "none";

            input.value = "";
            input.placeholder = "⏳ Adding follow-up task and running...";
            input.disabled = true;

            try {
                const res = await fetch(`${API_BASE}/api/goals/${goalId}/followup`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt: prompt, auto_run: true })
                });
                const data = await res.json();
                if (res.ok) {
                    await fetchGoals();
                    if (!window.goalPollTimer) {
                        window.goalPollTimer = setInterval(async () => {
                            const goals = await fetchGoals();
                            const isAnyRunning = goals && Array.isArray(goals) && goals.some(g => g.tasks && g.tasks.some(t => t.status === "in_progress"));
                            if (!isAnyRunning) {
                                clearInterval(window.goalPollTimer);
                                window.goalPollTimer = null;
                            }
                        }, 3000);
                    }
                } else {
                    alert("Error posting follow-up: " + (data.detail || JSON.stringify(data)));
                }
            } catch (err) {
                alert("Follow-up error: " + err.message);
            } finally {
                input.disabled = false;
                input.placeholder = "Ask follow-up (e.g. 'Where is the app code file?', 'Add dark mode')...";
            }
        }

        async function fetchReflections() {
            const list = document.getElementById("reflectionsList");
            try {
                const res = await fetch(`${API_BASE}/api/reflections`);
                const refs = await res.json();

                if (refs.length === 0) {
                    list.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">No reflections stored yet. Execute tasks to build agent self-memory.</div>`;
                    return;
                }

                list.innerHTML = refs.map(r => `
                    <div style="background: rgba(99, 102, 241, 0.08); border-left: 3px solid var(--primary); border-radius: 6px; padding: 1rem; font-size: 0.9rem; display: flex; flex-direction: column; gap: 0.4rem;">
                        <strong style="color: #c7d2fe;">${r.key || 'Reflection'}</strong>
                        <span style="color: var(--text-main); white-space: pre-wrap;">${r.content || ''}</span>
                    </div>
                `).join("");
            } catch (err) {
                list.innerHTML = `<div style="color: var(--accent-red);">Failed to load reflections.</div>`;
            }
        }

        async function pullModel(modelTag) {
            if (!confirm(`Are you sure you want to download and install model "${modelTag}" into local Ollama?`)) return;
            try {
                const res = await fetch(`${API_BASE}/api/models/pull`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ model_tag: modelTag })
                });
                const data = await res.json();
                alert("📥 " + (data.message || "Model download started in background. Refresh installed models once done!"));
                fetchInstalledModels();
            } catch (err) {
                alert("Failed to pull model: " + err.message);
            }
        }

        const userLikedModels = {};

        async function likeAndPullModel(modelTag, modelId, btnId) {
            userLikedModels[modelId] = true;
            const btn = document.getElementById(btnId);
            if (btn) {
                btn.style.background = "#ef4444";
                btn.style.color = "white";
                btn.innerHTML = "❤️ Liked & Pulling...";
            }
            await pullModel(modelTag);
        }

        async function fetchTrendingHFModels() {
            const list = document.getElementById("hfResultsList");
            if (!list) return;
            list.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">Fetching daily trending GGUF models from Hugging Face Hub...</div>`;

            try {
                const res = await fetch(`${API_BASE}/api/models/trending-hf`);
                const data = await res.json();

                if (!data.results || data.results.length === 0) {
                    list.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">Unable to load trending models right now. Try searching above!</div>`;
                    return;
                }

                list.innerHTML = data.results.map((m, idx) => {
                    const isLiked = !!userLikedModels[m.id];
                    const likeBtnId = `like_btn_tr_${idx}`;
                    const likeCount = (m.likes || 0) + (isLiked ? 1 : 0);
                    return `
                    <div style="background: rgba(9, 13, 22, 0.6); border: 1px solid var(--panel-border); border-radius: 10px; padding: 1rem; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <div style="display: flex; align-items: center; gap: 0.5rem;">
                                <strong style="color: var(--text-main); font-size: 0.95rem;">${m.id}</strong>
                                <span style="font-size: 0.72rem; padding: 0.15rem 0.5rem; border-radius: 12px; background: rgba(99, 102, 241, 0.2); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3);">GGUF Model</span>
                            </div>
                            <span style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-top: 0.2rem;">
                                📥 ${m.downloads.toLocaleString()} downloads | ❤️ ${likeCount.toLocaleString()} likes | Updated: ${m.updated_at || 'Recently'}
                            </span>
                        </div>
                        <div style="display: flex; gap: 0.4rem; align-items: center;">
                            <button id="${likeBtnId}" class="chip" onclick="likeAndPullModel('${m.ollama_tag}', '${m.id}', '${likeBtnId}')" style="font-size: 0.8rem; padding: 0.4rem 0.7rem; border-color: #ef4444; color: ${isLiked ? '#white' : '#f87171'}; background: ${isLiked ? '#ef4444' : 'rgba(239, 68, 68, 0.15)'};">
                                ${isLiked ? '❤️ Liked & Pulling' : '❤️ Like & Pull'}
                            </button>
                            <button class="btn-send" onclick="pullModel('${m.ollama_tag}')" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;">📥 Pull</button>
                            <button class="chip" onclick="navigator.clipboard.writeText('ollama run ${m.ollama_tag}'); alert('Copied to clipboard! Run this in your terminal: ollama run ${m.ollama_tag}');" style="padding: 0.4rem 0.7rem;">📋 Copy</button>
                        </div>
                    </div>
                `}).join("");
            } catch (err) {
                list.innerHTML = `<div style="color: var(--accent-red);">Failed to load trending models: ${err.message}</div>`;
            }
        }

        async function searchHFModels() {
            const query = document.getElementById("hfSearchInput").value.trim();
            const list = document.getElementById("hfResultsList");
            if (!query) return alert("Enter a search term!");

            list.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">Searching Hugging Face Hub for GGUF models matching "${query}"...</div>`;

            try {
                const res = await fetch(`${API_BASE}/api/models/search-hf?query=${encodeURIComponent(query)}`);
                const data = await res.json();

                if (!data.results || data.results.length === 0) {
                    list.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">No matching Hugging Face GGUF models found.</div>`;
                    return;
                }

                list.innerHTML = data.results.map((m, idx) => {
                    const isLiked = !!userLikedModels[m.id];
                    const likeBtnId = `like_btn_sr_${idx}`;
                    const likeCount = (m.likes || 0) + (isLiked ? 1 : 0);
                    return `
                    <div style="background: rgba(9, 13, 22, 0.6); border: 1px solid var(--panel-border); border-radius: 10px; padding: 1rem; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <div style="display: flex; align-items: center; gap: 0.5rem;">
                                <strong style="color: var(--text-main); font-size: 0.95rem;">${m.id}</strong>
                                <span style="font-size: 0.72rem; padding: 0.15rem 0.5rem; border-radius: 12px; background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);">Quantized GGUF</span>
                            </div>
                            <span style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-top: 0.2rem;">
                                📥 ${m.downloads.toLocaleString()} downloads | ❤️ ${likeCount.toLocaleString()} likes
                            </span>
                        </div>
                        <div style="display: flex; gap: 0.4rem; align-items: center;">
                            <button id="${likeBtnId}" class="chip" onclick="likeAndPullModel('${m.ollama_tag}', '${m.id}', '${likeBtnId}')" style="font-size: 0.8rem; padding: 0.4rem 0.7rem; border-color: #ef4444; color: ${isLiked ? '#white' : '#f87171'}; background: ${isLiked ? '#ef4444' : 'rgba(239, 68, 68, 0.15)'};">
                                ${isLiked ? '❤️ Liked & Pulling' : '❤️ Like & Pull'}
                            </button>
                            <button class="btn-send" onclick="pullModel('${m.ollama_tag}')" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;">📥 Pull</button>
                            <button class="chip" onclick="navigator.clipboard.writeText('ollama run ${m.ollama_tag}'); alert('Copied to clipboard! Run this in your terminal: ollama run ${m.ollama_tag}');" style="padding: 0.4rem 0.7rem;">📋 Copy</button>
                        </div>
                    </div>
                `}).join("");
            } catch (err) {
                list.innerHTML = `<div style="color: var(--accent-red);">Search failed: ${err.message}</div>`;
            }
        }

        let activeUploadedFilePath = "";

        async function handleFileUpload(event) {
            const files = event.target.files;
            if (!files || files.length === 0) return;
            const file = files[0];

            const formData = new FormData();
            formData.append("file", file);

            const uploadBtn = document.getElementById("btnUploadFile");
            uploadBtn.innerHTML = "⏳ Uploading...";
            uploadBtn.disabled = true;

            try {
                const res = await fetch(`${API_BASE}/api/upload`, {
                    method: "POST",
                    body: formData
                });
                const data = await res.json();
                if (res.ok && data.status === "success") {
                    activeUploadedFilePath = data.filepath;
                    document.getElementById("fileUploadInfo").innerText = `📄 Attached: ${data.filepath} (${(data.size / 1024).toFixed(1)} KB)`;
                    document.getElementById("fileUploadPreview").style.display = "flex";

                    const chatInput = document.getElementById("chatInput");
                    if (!chatInput.value.trim()) {
                        if (file.type.startsWith("image/")) {
                            chatInput.value = `Edit uploaded image ${data.filepath} using edit_image_sd_forge to `;
                        } else {
                            chatInput.value = `Analyze and extract details from uploaded file ${data.filepath} `;
                        }
                    }
                } else {
                    alert("Upload failed: " + (data.detail || data.message || "Unknown error"));
                }
            } catch (err) {
                alert("Upload error: " + err.message);
            } finally {
                uploadBtn.innerHTML = "📁 Upload File";
                uploadBtn.disabled = false;
                event.target.value = "";
            }
        }

        function clearFileUpload() {
            activeUploadedFilePath = "";
            document.getElementById("fileUploadPreview").style.display = "none";
        }

        async function fetchSystemStats() {
            try {
                const res = await fetch(`${API_BASE}/api/system/stats`);
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById("ramPct").innerText = `${data.ram_used_pct}%`;
                    document.getElementById("activeAgents").innerText = data.active_agents;
                    
                    if (data.gpu && data.gpu.gpu_available) {
                        document.getElementById("vramPct").innerText = `${data.gpu.vram_used_pct}%`;
                    } else {
                        document.getElementById("vramPct").innerText = `N/A`;
                    }

                    const badge = document.getElementById("memoryBadge");
                    const vramHigh = data.gpu && data.gpu.gpu_available && data.gpu.vram_used_pct >= 90.0;
                    const ramHigh = data.ram_used_pct >= 85.0;

                    if (ramHigh || vramHigh) {
                        badge.style.borderColor = "#ef4444";
                        badge.style.color = "#ef4444";
                    } else {
                        badge.style.borderColor = "var(--panel-border)";
                        badge.style.color = "#c7d2fe";
                    }
                }
            } catch (e) {
                console.warn("Stats fetch failed:", e);
            }
        }

        async function triggerGC() {
            try {
                const res = await fetch(`${API_BASE}/api/system/gc`, { method: "POST" });
                const data = await res.json();
                alert(`🧹 Memory cleanup completed!\nCollected ${data.collected_objects} unreferenced objects.\nAvailable RAM: ${data.free_ram_gb} GB`);
                fetchSystemStats();
            } catch (e) {
                alert("GC failed: " + e.message);
            }
        }

        // Initial Load & Timers
        fetchChatHistory();
        fetchInstalledModels();
        fetchGoals();
        fetchReflections();
        fetchSystemStats();
        setInterval(fetchSystemStats, 5000);
    
