/**
 * Anima Agent — ComfyUI sidebar panel.
 * Plan/run via HTTP; optionally load the built graph onto the canvas via app.loadGraphData.
 */
(function () {
  const EXT_NAME = "AgentAnima.Sidebar";

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach((k) => {
        if (k === "style" && typeof attrs[k] === "object") {
          Object.assign(node.style, attrs[k]);
        } else if (k === "className") {
          node.className = attrs[k];
        } else if (k.startsWith("on") && typeof attrs[k] === "function") {
          node.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
        } else {
          node.setAttribute(k, attrs[k]);
        }
      });
    }
    (children || []).forEach((c) => {
      if (c == null) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function downloadJson(filename, data) {
    try {
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      return true;
    } catch (e) {
      console.warn("[AgentAnima] download failed", e);
      return false;
    }
  }

  /**
   * Push UI workflow JSON onto the ComfyUI canvas.
   * Prefer app.loadGraphData (current frontend); fall back to graph.configure.
   */
  async function loadGraphToCanvas(uiWorkflow) {
    if (!uiWorkflow || !uiWorkflow.nodes) {
      throw new Error("ui_workflow missing nodes");
    }
    const app = window.app;
    if (!app) {
      throw new Error("window.app unavailable");
    }
    if (typeof app.loadGraphData === "function") {
      // ComfyUI frontend: replace current graph with workflow JSON
      const ret = app.loadGraphData(uiWorkflow);
      if (ret && typeof ret.then === "function") {
        await ret;
      }
      try {
        if (app.graph && typeof app.graph.setDirtyCanvas === "function") {
          app.graph.setDirtyCanvas(true, true);
        }
        if (app.canvas && typeof app.canvas.draw === "function") {
          app.canvas.draw(true, true);
        }
      } catch (_) {}
      return "app.loadGraphData";
    }
    if (app.graph && typeof app.graph.configure === "function") {
      app.graph.configure(uiWorkflow);
      return "app.graph.configure";
    }
    throw new Error("no loadGraphData / graph.configure on app");
  }

  function buildPanel() {
    const root = el("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        padding: "10px",
        color: "var(--fg-color, #ddd)",
        fontSize: "12px",
        minWidth: "280px",
      },
    });

    const title = el("div", { style: { fontWeight: "600", fontSize: "14px" } }, [
      "Anima Agent",
    ]);

    const textarea = el("textarea", {
      rows: "5",
      placeholder: "例如：雨夜里撑伞的银发少女，新海诚风格",
      style: {
        width: "100%",
        boxSizing: "border-box",
        resize: "vertical",
        minHeight: "80px",
        background: "var(--comfy-input-bg, #1e1e1e)",
        color: "inherit",
        border: "1px solid var(--border-color, #444)",
        borderRadius: "4px",
        padding: "6px",
      },
    });
    textarea.value = "雨夜里撑伞的银发少女，新海诚风格";

    const templateRow = el("div", {
      style: { display: "flex", gap: "6px", alignItems: "center" },
    });
    templateRow.appendChild(
      el("label", { style: { whiteSpace: "nowrap" } }, ["模板"])
    );
    const templateSelect = el("select", {
      style: {
        flex: "1",
        background: "var(--comfy-input-bg, #1e1e1e)",
        color: "inherit",
        border: "1px solid var(--border-color, #444)",
        borderRadius: "4px",
        padding: "4px",
      },
    });
    function setTemplateOptions(templates) {
      templateSelect.innerHTML = "";
      const auto = el("option", { value: "auto" }, ["自动"]);
      templateSelect.appendChild(auto);
      (templates || []).forEach((t) => {
        const label =
          (t.title || t.id) + (t.available === false ? " (未发现)" : "");
        const opt = el("option", { value: t.id }, [label]);
        if (t.available === false) opt.disabled = true;
        templateSelect.appendChild(opt);
      });
    }
    setTemplateOptions([
      { id: "stock_anima", title: "原生 Anima", available: true },
      { id: "easyuse_aio", title: "EasyUse AiO", available: true },
      { id: "spectrum_ksampler", title: "Spectrum KSampler", available: true },
      {
        id: "anima_ref_adapter",
        title: "Anima Ref Adapter（参考图锁人物）",
        available: true,
      },
    ]);
    templateRow.appendChild(templateSelect);

    const refRow = el("div", {
      style: { display: "flex", gap: "6px", alignItems: "center" },
    });
    refRow.appendChild(
      el("label", { style: { whiteSpace: "nowrap" } }, ["参考图"])
    );
    const refInput = el("input", {
      type: "text",
      placeholder: "input 目录文件名，如 char.png",
      style: {
        flex: "1",
        background: "var(--comfy-input-bg, #1e1e1e)",
        color: "inherit",
        border: "1px solid var(--border-color, #444)",
        borderRadius: "4px",
        padding: "4px",
      },
    });
    refRow.appendChild(refInput);

    const canvasRow = el("div", {
      style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" },
    });
    const loadCanvasLabel = el(
      "label",
      { style: { display: "flex", gap: "4px", alignItems: "center", cursor: "pointer" } },
      []
    );
    const loadCanvasCheck = el("input", { type: "checkbox" });
    loadCanvasCheck.checked = true;
    loadCanvasLabel.appendChild(loadCanvasCheck);
    loadCanvasLabel.appendChild(document.createTextNode("显示到画布"));
    canvasRow.appendChild(loadCanvasLabel);

    const downloadCheckLabel = el(
      "label",
      { style: { display: "flex", gap: "4px", alignItems: "center", cursor: "pointer" } },
      []
    );
    const downloadCheck = el("input", { type: "checkbox" });
    downloadCheck.checked = false;
    downloadCheckLabel.appendChild(downloadCheck);
    downloadCheckLabel.appendChild(document.createTextNode("下载 UI JSON"));
    canvasRow.appendChild(downloadCheckLabel);

    fetch("/agent_anima/capabilities")
      .then((r) => r.json())
      .then((data) => {
        if (data && data.templates) setTemplateOptions(data.templates);
      })
      .catch(() => {});

    const row = el("div", { style: { display: "flex", gap: "6px", flexWrap: "wrap" } });
    const runBtn = el(
      "button",
      {
        style: {
          flex: "1",
          padding: "6px 10px",
          cursor: "pointer",
          background: "#3d5afe",
          color: "#fff",
          border: "none",
          borderRadius: "4px",
        },
      },
      ["Run"]
    );
    const planBtn = el(
      "button",
      {
        style: {
          padding: "6px 10px",
          cursor: "pointer",
          background: "#333",
          color: "#fff",
          border: "1px solid #555",
          borderRadius: "4px",
        },
      },
      ["Plan only"]
    );
    const showBtn = el(
      "button",
      {
        style: {
          padding: "6px 10px",
          cursor: "pointer",
          background: "#1b5e20",
          color: "#fff",
          border: "none",
          borderRadius: "4px",
        },
        title: "只构建并显示到画布，不排队",
      },
      ["显示到画布"]
    );
    row.appendChild(runBtn);
    row.appendChild(planBtn);
    row.appendChild(showBtn);

    const status = el("pre", {
      style: {
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        maxHeight: "220px",
        overflow: "auto",
        margin: "0",
        padding: "6px",
        background: "rgba(0,0,0,0.25)",
        borderRadius: "4px",
        fontSize: "11px",
      },
    });
    status.textContent = "Ready.";

    let lastUiWorkflow = null;

    async function post(path, body) {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await res.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch (e) {
        throw new Error("Non-JSON response: " + text.slice(0, 200));
      }
      if (!res.ok && data && data.error) {
        throw new Error(data.error);
      }
      return data;
    }

    function requestBody(extra) {
      const body = Object.assign(
        {
          command: textarea.value.trim(),
          template: templateSelect.value || "auto",
          ref_image: (refInput.value || "").trim() || undefined,
          load_to_canvas: !!loadCanvasCheck.checked,
        },
        extra || {}
      );
      return body;
    }

    async function maybeShowOnCanvas(data, force) {
      const ui = data && data.ui_workflow;
      if (!ui) return "no ui_workflow";
      lastUiWorkflow = ui;
      if (downloadCheck.checked) {
        downloadJson(
          "agent_anima_" + (data.template_used || "workflow") + ".json",
          ui
        );
      }
      if (!force && !loadCanvasCheck.checked) {
        return "skipped (checkbox off)";
      }
      try {
        const via = await loadGraphToCanvas(ui);
        return "loaded via " + via;
      } catch (e) {
        console.warn("[AgentAnima] canvas load failed", e);
        // Offer download so user can File → Open
        downloadJson(
          "agent_anima_" + (data.template_used || "workflow") + ".json",
          ui
        );
        return "canvas load failed: " + (e && e.message ? e.message : e) + "; downloaded JSON";
      }
    }

    runBtn.addEventListener("click", async () => {
      const command = textarea.value.trim();
      if (!command) {
        status.textContent = "Please enter a command.";
        return;
      }
      runBtn.disabled = true;
      status.textContent = "Running (plan → queue → wait)…";
      try {
        const data = await post(
          "/agent_anima/run",
          requestBody({ wait: true })
        );
        const canvasNote = await maybeShowOnCanvas(data, false);
        const lines = [
          "ok=" + data.ok,
          "template=" + (data.template_used || ""),
          "prompt_id=" + (data.prompt_id || ""),
          "images=" + ((data.images && data.images.length) || 0),
          "canvas=" + canvasNote,
          "",
          "POSITIVE:",
          data.positive_prompt || "",
          "",
          "NEGATIVE:",
          (data.negative_prompt || "").slice(0, 400) + "…",
        ];
        if (data.image_urls && data.image_urls.length) {
          lines.push("", "URLs:");
          data.image_urls.forEach((u) => lines.push(u));
        }
        if (data.error) lines.push("", "error: " + JSON.stringify(data.error));
        status.textContent = lines.join("\n");
      } catch (e) {
        status.textContent = "Error: " + (e && e.message ? e.message : e);
      } finally {
        runBtn.disabled = false;
      }
    });

    planBtn.addEventListener("click", async () => {
      const command = textarea.value.trim();
      if (!command) {
        status.textContent = "Please enter a command.";
        return;
      }
      status.textContent = "Planning…";
      try {
        const data = await post("/agent_anima/plan", requestBody());
        const canvasNote = await maybeShowOnCanvas(data, false);
        status.textContent = [
          "template_used=" + (data.template_used || ""),
          "capabilities_note=" + (data.capabilities_note || ""),
          "canvas=" + canvasNote,
          "ui_nodes=" + ((data.ui_summary && data.ui_summary.node_count) || 0),
          "",
          "POSITIVE:",
          data.positive_prompt || "",
          "",
          "NEGATIVE:",
          data.negative_prompt || "",
          "",
          "NOTES:",
          data.notes || "",
          "",
          "PLAN:",
          JSON.stringify(data.plan, null, 2),
        ].join("\n");
      } catch (e) {
        status.textContent = "Error: " + (e && e.message ? e.message : e);
      }
    });

    showBtn.addEventListener("click", async () => {
      const command = textarea.value.trim();
      if (!command) {
        status.textContent = "Please enter a command.";
        return;
      }
      status.textContent = "Building UI workflow…";
      try {
        const data = await post("/agent_anima/load_ui", requestBody());
        const canvasNote = await maybeShowOnCanvas(data, true);
        status.textContent = [
          "ok=" + data.ok,
          "template_used=" + (data.template_used || ""),
          "canvas=" + canvasNote,
          "ui_summary=" + JSON.stringify(data.ui_summary || {}),
          "",
          "提示：若画布未更新，可用「下载 UI JSON」后通过 ComfyUI File → Open 打开。",
        ].join("\n");
      } catch (e) {
        // Fallback: if we already have a last graph, try loading it
        if (lastUiWorkflow) {
          try {
            const via = await loadGraphToCanvas(lastUiWorkflow);
            status.textContent =
              "load_ui failed (" +
              (e && e.message ? e.message : e) +
              "); reloaded last ui_workflow via " +
              via;
            return;
          } catch (_) {}
        }
        status.textContent = "Error: " + (e && e.message ? e.message : e);
      }
    });

    root.appendChild(title);
    root.appendChild(textarea);
    root.appendChild(templateRow);
    root.appendChild(refRow);
    root.appendChild(canvasRow);
    root.appendChild(row);
    root.appendChild(status);
    return root;
  }

  function ensureFloatLauncher() {
    if (document.getElementById("agent-anima-fab")) return;
    const fab = el(
      "button",
      {
        id: "agent-anima-fab",
        title: "Anima Agent",
        style: {
          position: "fixed",
          right: "18px",
          bottom: "18px",
          zIndex: "10000",
          padding: "10px 14px",
          borderRadius: "999px",
          border: "1px solid #666",
          background: "#2a2a2a",
          color: "#eee",
          cursor: "pointer",
          boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
          fontSize: "13px",
        },
        onClick: () => {
          let box = document.getElementById("agent-anima-float");
          if (box) {
            box.style.display = box.style.display === "none" ? "block" : "none";
            return;
          }
          box = el("div", {
            id: "agent-anima-float",
            style: {
              position: "fixed",
              right: "18px",
              bottom: "64px",
              width: "360px",
              maxHeight: "80vh",
              overflow: "auto",
              zIndex: "9999",
              background: "var(--comfy-menu-bg, #222)",
              border: "1px solid #555",
              borderRadius: "8px",
              boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
            },
          });
          box.appendChild(buildPanel());
          document.body.appendChild(box);
        },
      },
      ["Anima Agent"]
    );
    document.body.appendChild(fab);
  }

  function tryRegister() {
    if (!window.app || typeof window.app.registerExtension !== "function") {
      return false;
    }
    window.app.registerExtension({
      name: EXT_NAME,
      async setup() {
        try {
          if (
            window.app.extensionManager &&
            window.app.extensionManager.registerSidebarTab
          ) {
            window.app.extensionManager.registerSidebarTab({
              id: "agent-anima",
              icon: "pi pi-bolt",
              title: "Anima Agent",
              tooltip: "Anima Agent — NL → workflow",
              type: "custom",
              render: (elContainer) => {
                elContainer.appendChild(buildPanel());
              },
            });
            ensureFloatLauncher();
            return;
          }
        } catch (e) {
          console.warn("[AgentAnima] sidebar tab failed", e);
        }

        try {
          ensureFloatLauncher();
          const menu = document.querySelector(".comfy-menu");
          if (!menu) return;
          const btn = el(
            "button",
            {
              style: { margin: "4px", cursor: "pointer" },
              onClick: () => {
                let box = document.getElementById("agent-anima-float");
                if (box) {
                  box.style.display =
                    box.style.display === "none" ? "block" : "none";
                  return;
                }
                box = el("div", {
                  id: "agent-anima-float",
                  style: {
                    position: "fixed",
                    right: "16px",
                    bottom: "16px",
                    width: "340px",
                    zIndex: "9999",
                    background: "var(--comfy-menu-bg, #222)",
                    border: "1px solid #555",
                    borderRadius: "8px",
                    boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
                  },
                });
                box.appendChild(buildPanel());
                document.body.appendChild(box);
              },
            },
            ["Anima Agent"]
          );
          menu.appendChild(btn);
        } catch (e) {
          console.warn("[AgentAnima] menu fallback failed", e);
        }
      },
    });
    return true;
  }

  if (!tryRegister()) {
    const t = setInterval(() => {
      if (tryRegister()) clearInterval(t);
    }, 250);
    setTimeout(() => clearInterval(t), 15000);
  }
})();
