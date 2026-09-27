/* ============================================================
   SCRIPTS.JS — Setup Wizard Logic + Task Detail Auto-Refresh
   (Mobile nav is now handled by common.js)
   ============================================================ */

document.addEventListener("DOMContentLoaded", function () {

  // --- Auto-refresh logs on the task detail page ---
  const autoRefreshCheckbox = document.getElementById("auto-refresh");
  if (autoRefreshCheckbox) {
    const logContainer = document.querySelector(".log-viewer");
    const refreshState = document.getElementById("task-log-refresh-state");
    const statusBadge = document.getElementById("task-status-badge");
    const scheduleBadge = document.getElementById("task-schedule-badge");
    const manageScheduleBtn = document.getElementById("manage-schedule-btn");
    let currentScheduleCanEnable = manageScheduleBtn
      ? manageScheduleBtn.dataset.scheduleCanEnable === "true"
      : false;
    const taskName = autoRefreshCheckbox.getAttribute("data-task-name");
    const logLines = autoRefreshCheckbox.getAttribute("data-log-lines") || "500";
    let intervalId;
    let initialLoad = true;
    let failedFetchCount = 0;

    function scrollToBottom() {
      if (logContainer) logContainer.scrollTop = logContainer.scrollHeight;
    }

    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function ansiCodesToClass(codes) {
      const parts = codes.split(";").filter(Boolean);
      const classes = [];
      let isBright = false;
      parts.forEach((part) => {
        if (part === "1") isBright = true;
        if (part === "31") classes.push("ansi-red");
        if (part === "32") classes.push("ansi-green");
        if (part === "33") classes.push("ansi-yellow");
        if (part === "34") classes.push("ansi-blue");
        if (part === "35") classes.push("ansi-magenta");
        if (part === "36") classes.push("ansi-cyan");
        if (part === "37") classes.push("ansi-white");
      });
      if (isBright && classes.length) classes.push("ansi-bright");
      return classes.join(" ");
    }

    function renderAnsiLog(text) {
      // Process each line independently so color cannot spill across lines
      // (handles truncated logs that start mid-color-block).
      const ansiPattern = /\x1b\[([0-9;]*)m/g;
      return text.split("\n").map(function (line) {
        let html = "";
        let open = false;
        let lastIndex = 0;
        let match;
        ansiPattern.lastIndex = 0;
        while ((match = ansiPattern.exec(line)) !== null) {
          html += escapeHtml(line.slice(lastIndex, match.index));
          if (open) { html += "</span>"; open = false; }
          const className = ansiCodesToClass(match[1] || "0");
          if (className) { html += `<span class="${className}">`; open = true; }
          lastIndex = ansiPattern.lastIndex;
        }
        html += escapeHtml(line.slice(lastIndex));
        if (open) html += "</span>";
        return html;
      }).join("\n");
    }

    function renderTaskStatusBadge(status) {
      if (status === "Success") return '<span class="badge badge-success"><i class="fas fa-circle-check"></i> Success</span>';
      if (status === "Failure") return '<span class="badge badge-danger"><i class="fas fa-circle-xmark"></i> Failure</span>';
      if (status === "Running") return '<span class="badge badge-info"><i class="fas fa-spinner fa-spin"></i> Running</span>';
      if (status === "Missing") return '<span class="badge badge-warning"><i class="fas fa-circle-exclamation"></i> Missing</span>';
      if (status === "Not Run Yet") return '<span class="badge badge-neutral"><i class="fas fa-clock"></i> Not Run Yet</span>';
      if (status === "Stopped") return '<span class="badge badge-neutral"><i class="fas fa-stop"></i> Stopped</span>';
      return `<span class="badge badge-warning"><i class="fas fa-question-circle"></i> ${escapeHtml(status || "Unknown")}</span>`;
    }

    function scheduleBadgeMeta(schedule) {
      const state = schedule && schedule.state;
      // Schedule severity is separate from the task run status badge shown beside it.
      if (["temporary", "permanent", "restore_failed", "external_disabled"].includes(state)) {
        return { className: "badge-schedule-danger", iconClass: "fa-calendar-xmark" };
      }
      if (state === "issue") {
        return { className: "badge-schedule-warning", iconClass: "fa-triangle-exclamation" };
      }
      return { className: "badge-neutral", iconClass: "fa-calendar-days" };
    }

    function fetchTaskStatus() {
      if (!statusBadge) return Promise.resolve();
      return fetch(`/api/tasks/${encodeURIComponent(taskName)}/status`, {
        headers: { "Accept": "application/json" }
      })
        .then((resp) => {
          if (!resp.ok) throw new Error(`Task status refresh failed with HTTP ${resp.status}`);
          return resp.json();
        })
        .then((payload) => {
          const task = payload && payload.data ? payload.data.task : null;
          statusBadge.innerHTML = renderTaskStatusBadge(task && task.status);
          updateScheduleControls(task && task.schedule);
        });
    }

    function updateScheduleControls(schedule) {
      if (!schedule) return;
      if (scheduleBadge) {
        const badgeMeta = scheduleBadgeMeta(schedule);
        scheduleBadge.className = `badge ${badgeMeta.className}`;
        scheduleBadge.innerHTML = `<i class="fas ${badgeMeta.iconClass}"></i> ${escapeHtml(schedule.label || "Unknown")}`;
      }
      currentScheduleCanEnable = Boolean(schedule.can_enable);
      if (manageScheduleBtn) {
        manageScheduleBtn.dataset.scheduleCanEnable = currentScheduleCanEnable ? "true" : "false";
      }
    }

    async function enableSchedule() {
      window.AsyncButtonState.start(manageScheduleBtn);
      try {
        const response = await window.ApiClient.fetchJson(
          `/task/${encodeURIComponent(taskName)}/enable-schedule`,
          {
            method: "POST",
            headers: { "Accept": "application/json" }
          }
        );
        window.AsyncButtonState.success(manageScheduleBtn);
        updateScheduleControls(response.data && response.data.task && response.data.task.schedule);
        showAlert(response.message || "Schedule enabled.", "success");
      } catch (error) {
        window.AsyncButtonState.error(manageScheduleBtn);
        showAlert(error.message || "Schedule enable failed.", "danger");
      }
    }

    function fetchLogs() {
      const distanceFromBottom = logContainer
        ? logContainer.scrollHeight - logContainer.scrollTop - logContainer.clientHeight
        : 0;
      const stickToBottom = distanceFromBottom < 48;

      return fetch(`/task/${encodeURIComponent(taskName)}/logs?lines=${encodeURIComponent(logLines)}`)
        .then((resp) => {
          if (!resp.ok) throw new Error(`Log refresh failed with HTTP ${resp.status}`);
          return resp.text();
        })
        .then((text) => {
          failedFetchCount = 0;
          if (refreshState) refreshState.textContent = "";
          if (logContainer) logContainer.innerHTML = renderAnsiLog(text);
          if (initialLoad) {
            scrollToBottom();
            initialLoad = false;
          } else if (logContainer && stickToBottom) {
            scrollToBottom();
          }
        })
        .catch((err) => {
          failedFetchCount += 1;
          if (refreshState) {
            refreshState.textContent = failedFetchCount > 1
              ? "Reconnecting to log..."
              : "Log refresh paused; retrying...";
          }
          console.error(err);
        });
    }

    function refreshTaskDetail() {
      fetchTaskStatus().catch((err) => console.error(err));
      fetchLogs();
    }

    function start() {
      refreshTaskDetail();
      intervalId = setInterval(refreshTaskDetail, 1000);
    }

    function stop() {
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    }

    autoRefreshCheckbox.addEventListener("change", () => {
      if (autoRefreshCheckbox.checked) {
        start();
      } else {
        stop();
      }
    });

    scrollToBottom();
    start();

    const disableScheduleControl = window.TaskScheduleControl
      ? window.TaskScheduleControl.createDisableScheduleController({
        taskName,
        onScheduleChanged: updateScheduleControls
      })
      : null;

    if (manageScheduleBtn) {
      manageScheduleBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const items = [
          {
            label: "Disable Schedule...",
            iconClass: "fas fa-calendar-xmark me-2",
            destructive: true,
            onSelect: () => {
              if (disableScheduleControl) disableScheduleControl.open();
            }
          },
          {
            label: "Enable Schedule",
            iconClass: "fas fa-calendar-check me-2",
            disabled: !currentScheduleCanEnable,
            onSelect: () => enableSchedule()
          }
        ];
        window.ActionContextMenu.show(items, event.clientX, event.clientY);
      });
    }
  }

});
