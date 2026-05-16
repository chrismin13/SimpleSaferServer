window.TaskScheduleControl = (() => {
  function selectedDisableDuration() {
    const selected = document.querySelector('input[name="disableScheduleDuration"]:checked');
    return selected ? selected.value : "1";
  }

  function parseDisablePayload(customHoursInput, statusEl) {
    let duration = selectedDisableDuration();
    statusEl.textContent = "";
    if (duration === "custom") {
      if (!customHoursInput) return null;
      const customVal = customHoursInput.value.trim();
      if (!/^\d+$/.test(customVal)) {
        statusEl.textContent = "Custom duration must contain only digits.";
        return null;
      }
      const hours = parseInt(customVal, 10);
      if (isNaN(hours) || hours <= 0) {
        statusEl.textContent = "Custom duration must be greater than 0 hours.";
        return null;
      }
      duration = String(hours);
    }
    return duration === "permanent"
      ? { mode: "permanent" }
      : { mode: "temporary", hours: Number(duration) };
  }

  function createDisableScheduleController(options) {
    const modal = document.getElementById("disableScheduleModal");
    const confirm = document.getElementById("disableScheduleConfirm");
    const cancel = document.getElementById("disableScheduleCancel");
    const close = document.getElementById("disableScheduleClose");
    const status = document.getElementById("disableScheduleStatus");
    const permanentNote = document.getElementById("disableSchedulePermanentNote");
    const customGroup = document.getElementById("disableScheduleCustomGroup");
    const customHoursInput = document.getElementById("disableScheduleCustomHours");
    if (!modal || !confirm || !status) return null;

    function taskName() {
      return typeof options.taskName === "function" ? options.taskName() : options.taskName;
    }

    function open() {
      status.textContent = "";
      modal.classList.remove("d-none");
      modal.classList.add("visible");
      modal.setAttribute("aria-hidden", "false");
    }

    function closeModal() {
      modal.classList.add("d-none");
      modal.classList.remove("visible");
      modal.setAttribute("aria-hidden", "true");
    }

    async function disableSchedule() {
      const currentTaskName = taskName();
      if (!currentTaskName) return;
      const payload = parseDisablePayload(customHoursInput, status);
      if (!payload) return;

      window.AsyncButtonState.start(confirm);
      try {
        const response = await window.ApiClient.fetchJson(
          `/task/${encodeURIComponent(currentTaskName)}/disable-schedule`,
          {
            method: "POST",
            headers: { "Accept": "application/json", "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          }
        );
        window.AsyncButtonState.success(confirm);
        // Each page owns its schedule badge/menu state, so the shared control hands back the API summary.
        if (typeof options.onScheduleChanged === "function") {
          options.onScheduleChanged(response.data && response.data.task && response.data.task.schedule);
        }
        closeModal();
        showAlert(response.message || "Schedule disabled.", "success");
      } catch (error) {
        window.AsyncButtonState.error(confirm);
        status.textContent = error.message || "Schedule disable failed.";
      }
    }

    confirm.addEventListener("click", disableSchedule);
    [cancel, close].forEach((button) => {
      if (button) button.addEventListener("click", closeModal);
    });
    document.querySelectorAll('input[name="disableScheduleDuration"]').forEach((input) => {
      input.addEventListener("change", () => {
        const val = selectedDisableDuration();
        if (permanentNote) {
          permanentNote.classList.toggle("d-none", val !== "permanent");
        }
        if (customGroup) {
          const isCustom = val === "custom";
          customGroup.classList.toggle("d-none", !isCustom);
          if (isCustom && customHoursInput) {
            customHoursInput.focus();
          }
        }
      });
    });

    return { open, close: closeModal };
  }

  return { createDisableScheduleController };
})();
