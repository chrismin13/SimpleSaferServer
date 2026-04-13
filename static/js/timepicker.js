/**
 * Universal Time Picker (Bunker theme)
 * A custom, scroll-snapping time picker for a premium aesthetic across all browsers.
 */

class BunkerTimePicker {
  constructor(inputEl) {
    this.input = inputEl;
    if (this.input.dataset.timePickerInitialized) return;
    this.input.dataset.timePickerInitialized = 'true';

    // Change input to text and readonly to prevent native picker and keyboard
    this.input.type = 'text';
    this.input.readOnly = true;
    this.input.classList.add('bunker-time-input');

    this.isOpen = false;
    this.popover = null;
    this.hourCol = null;
    this.minuteCol = null;

    // Default or current time
    this.currentHour = 0;
    this.currentMinute = 0;
    this.parseInput();

    this.bindEvents();
  }

  parseInput() {
    const val = this.input.value;
    if (val && /^\d{2}:\d{2}$/.test(val)) {
      const parts = val.split(':');
      this.currentHour = parseInt(parts[0], 10);
      this.currentMinute = parseInt(parts[1], 10);
    } else {
      // Default to 3:00 AM
      this.currentHour = 3;
      this.currentMinute = 0;
    }
  }

  formatValue(hour, min) {
    const h = hour.toString().padStart(2, '0');
    const m = min.toString().padStart(2, '0');
    return `${h}:${m}`;
  }

  bindEvents() {
    this.input.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggle();
    });

    document.addEventListener('click', (e) => {
      if (this.isOpen && this.popover && !this.popover.contains(e.target) && e.target !== this.input) {
        this.close();
      }
    });
  }

  buildPopover() {
    if (this.popover) return;

    this.popover = document.createElement('div');
    this.popover.className = 'bunker-time-picker-popover';

    const container = document.createElement('div');
    container.className = 'bunker-tcp-container';

    // Highlight frame in the center
    const highlight = document.createElement('div');
    highlight.className = 'bunker-tcp-highlight';

    this.hourCol = document.createElement('div');
    this.hourCol.className = 'bunker-tcp-col bunker-tcp-hours';

    this.minuteCol = document.createElement('div');
    this.minuteCol.className = 'bunker-tcp-col bunker-tcp-minutes';

    const colon = document.createElement('div');
    colon.className = 'bunker-tcp-colon';
    colon.textContent = ':';

    this.populateColumn(this.hourCol, 24);
    this.populateColumn(this.minuteCol, 60);

    container.appendChild(highlight);
    container.appendChild(this.hourCol);
    container.appendChild(colon);
    container.appendChild(this.minuteCol);

    const footer = document.createElement('div');
    footer.className = 'bunker-tcp-footer';

    const doneBtn = document.createElement('button');
    doneBtn.type = 'button';
    doneBtn.className = 'btn btn-primary btn-sm btn-block';
    doneBtn.innerHTML = 'Done';
    doneBtn.addEventListener('click', () => this.close());
    footer.appendChild(doneBtn);

    this.popover.appendChild(container);
    this.popover.appendChild(footer);

    document.body.appendChild(this.popover);

    // Setup scrolling logic after attaching
    this.setupScrollLogic(this.hourCol, 24, (val) => {
      this.currentHour = val;
      this.updateInput();
    });
    this.setupScrollLogic(this.minuteCol, 60, (val) => {
      this.currentMinute = val;
      this.updateInput();
    });
  }

  populateColumn(col, max) {
    // Add spacer at top
    col.appendChild(this.createSpacer());
    // Add numbers
    for (let i = 0; i < max; i++) {
      const item = document.createElement('div');
      item.className = 'bunker-tcp-item';
      item.textContent = i.toString().padStart(2, '0');
      item.dataset.value = i;

      item.addEventListener('click', (e) => {
        e.stopPropagation();
        this.scrollToValue(col, i);
      });

      col.appendChild(item);
    }
    // Add spacer at bottom
    col.appendChild(this.createSpacer());
  }

  createSpacer() {
    const spacer = document.createElement('div');
    spacer.className = 'bunker-tcp-spacer';
    return spacer;
  }

  setupScrollLogic(col, max, onChange) {
    let isScrolling;
    let targetVal = null;

    col.addEventListener('scroll', () => {
      window.clearTimeout(isScrolling);
      isScrolling = setTimeout(() => {
        this.updateActiveItem(col, onChange);
        targetVal = null;
      }, 60);
    });

    col.addEventListener('wheel', (e) => {
      // Only intercept vertical scrolling
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;

      // Heuristic to detect discrete mouse wheels vs continuous trackpads.
      // Standard mouse wheels transmit in line mode (Firefox) or in large, 
      // round numbers of pixels (Chrome: 100, 120, 150). Trackpads send granular fluid data.
      const isDiscreteWheel = e.deltaMode === 1 ||
        (e.deltaMode === 0 && Math.abs(e.deltaY) >= 40 && Math.abs(e.deltaY) % 10 === 0);

      // Allow native browser physics for Trackpads!
      if (!isDiscreteWheel) return;

      // Stop discrete wheels from skipping multiple elements natively
      e.preventDefault();

      const active = col.querySelector('.bunker-tcp-item.active');
      if (!active) return;

      // Use the intended target if we are mid-animation, otherwise use current
      let currentVal = targetVal !== null ? targetVal : parseInt(active.dataset.value, 10);

      // Move 1 item per normal threshold tick. Mouse wheels usually push 100 or 120 delta.
      let ticks = Math.sign(e.deltaY) * Math.max(1, Math.round(Math.abs(e.deltaY) / 100));
      if (e.deltaMode === 1) ticks = Math.sign(e.deltaY); // Firefox single line = 1 tick

      let nextVal = currentVal + ticks;
      if (nextVal < 0) nextVal = 0;
      if (nextVal >= max) nextVal = max - 1;

      if (nextVal !== currentVal || targetVal === null) {
        targetVal = nextVal;
        this.scrollToValue(col, nextVal);
      }
    }, { passive: false });
  }

  updateActiveItem(col, onChange) {
    const items = col.querySelectorAll('.bunker-tcp-item');
    const colCenter = col.getBoundingClientRect().top + col.clientHeight / 2;
    let closestItem = null;
    let minDiff = Infinity;

    items.forEach(item => {
      const rect = item.getBoundingClientRect();
      const itemCenter = rect.top + rect.height / 2;
      const diff = Math.abs(colCenter - itemCenter);

      if (diff < minDiff) {
        minDiff = diff;
        closestItem = item;
      }
      item.classList.remove('active');
    });

    if (closestItem) {
      closestItem.classList.add('active');
      const val = parseInt(closestItem.dataset.value, 10);
      if (typeof onChange === 'function') onChange(val);
    }
  }

  scrollToValue(col, val) {
    const items = col.querySelectorAll('.bunker-tcp-item');
    const target = Array.from(items).find(item => parseInt(item.dataset.value, 10) === val);
    if (target) {
      // scroll to center
      const offset = target.offsetTop - col.clientHeight / 2 + target.clientHeight / 2;
      col.scrollTop = offset;

      items.forEach(i => i.classList.remove('active'));
      target.classList.add('active');
    }
  }

  updateInput() {
    const val = this.formatValue(this.currentHour, this.currentMinute);
    this.input.value = val;
    // Dispatch input change event so listeners (like validation) can trigger
    this.input.dispatchEvent(new Event('input', { bubbles: true }));
    this.input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  positionPopover() {
    const rect = this.input.getBoundingClientRect();
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

    // Check space below
    const spaceBelow = window.innerHeight - rect.bottom;
    const popoverHeight = 280; // approximate internal height

    let top;
    if (spaceBelow < popoverHeight && rect.top > popoverHeight) {
      // Show above
      top = rect.top + scrollTop - popoverHeight - 8;
    } else {
      // Show below
      top = rect.bottom + scrollTop + 8;
    }

    this.popover.style.top = `${top}px`;

    // Align horizontally to the left edge of the input
    let left = rect.left;

    // Keep in screen bounds (minimum 16px from left edge, maximum padding from right)
    if (left < 16) left = 16;
    if (left + 250 > window.innerWidth - 16) left = window.innerWidth - 250 - 16;

    this.popover.style.left = `${left}px`;
  }

  open() {
    this.parseInput();
    this.buildPopover();

    // Make visible briefly to grab layout, but transparent
    this.popover.style.display = 'block';
    this.popover.style.opacity = '0';
    this.positionPopover();

    // Force reflow
    void this.popover.offsetWidth;

    this.popover.classList.add('visible');
    this.popover.style.opacity = '1';

    // Scroll to current values
    setTimeout(() => {
      this.scrollToValue(this.hourCol, this.currentHour);
      this.scrollToValue(this.minuteCol, this.currentMinute);
    }, 10);

    this.isOpen = true;
  }

  close() {
    if (!this.isOpen || !this.popover) return;
    this.popover.classList.remove('visible');

    setTimeout(() => {
      if (this.popover && !this.popover.classList.contains('visible')) {
        this.popover.style.display = 'none';
      }
    }, 200);

    this.isOpen = false;
  }

  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  static initAll() {
    document.querySelectorAll('input[type="time"]').forEach(input => {
      new BunkerTimePicker(input);
    });
  }
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  BunkerTimePicker.initAll();
});
