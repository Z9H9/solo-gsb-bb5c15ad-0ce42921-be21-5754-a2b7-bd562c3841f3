/* 编织行指令审校工具 —— 前端逻辑（原生 JS，无框架） */

(function () {
  "use strict";

  const rowsEl = document.getElementById("rows");
  const startEl = document.getElementById("startCount");
  const summaryEl = document.getElementById("summary");
  const importFileEl = document.getElementById("importFile");

  const EXAMPLE = {
    start: 12,
    rows: [
      "k12",
      "[inc2 k1]*6",
      "[k2 dec2]*4 k2",
      "[dec2 k1]*5",
    ],
  };

  /* ---------------- 行 DOM ---------------- */

  function createRow(value) {
    const div = document.createElement("div");
    div.className = "row";

    const no = document.createElement("span");
    no.className = "row-no";

    const main = document.createElement("div");
    main.className = "row-main";

    const input = document.createElement("input");
    input.className = "row-src";
    input.type = "text";
    input.spellcheck = false;
    input.placeholder = "如：k2 [inc2 k1]*3";
    input.value = value == null ? "" : value;
    input.addEventListener("input", scheduleEvaluate);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        insertRowAfter(div, "");
      }
    });

    const highlight = document.createElement("div");
    highlight.className = "row-highlight";
    highlight.hidden = true;

    const msg = document.createElement("div");
    msg.className = "row-msg";
    msg.hidden = true;

    const expand = document.createElement("details");
    expand.className = "row-expand";
    expand.hidden = true;
    const expandSummary = document.createElement("summary");
    const expandCode = document.createElement("code");
    expand.appendChild(expandSummary);
    expand.appendChild(expandCode);

    main.appendChild(input);
    main.appendChild(highlight);
    main.appendChild(msg);
    main.appendChild(expand);

    const stats = document.createElement("div");
    stats.className = "row-stats";
    const statEls = {};
    [["avail", "可用"], ["cons", "消耗"], ["prod", "产出"], ["rem", "剩余"]].forEach(
      function (pair) {
        const span = document.createElement("span");
        span.className = "stat";
        const em = document.createElement("em");
        em.textContent = pair[1];
        const b = document.createElement("b");
        b.textContent = "–";
        span.appendChild(em);
        span.appendChild(b);
        stats.appendChild(span);
        statEls[pair[0]] = b;
      }
    );

    const ops = document.createElement("div");
    ops.className = "row-ops";
    const insertBtn = document.createElement("button");
    insertBtn.className = "icon-btn insert";
    insertBtn.type = "button";
    insertBtn.title = "在下方插入一行";
    insertBtn.textContent = "＋";
    insertBtn.addEventListener("click", function () {
      insertRowAfter(div, "");
    });
    const delBtn = document.createElement("button");
    delBtn.className = "icon-btn del";
    delBtn.type = "button";
    delBtn.title = "删除此行";
    delBtn.textContent = "×";
    delBtn.addEventListener("click", function () {
      div.remove();
      renumber();
      scheduleEvaluate();
    });
    ops.appendChild(insertBtn);
    ops.appendChild(delBtn);

    div.appendChild(no);
    div.appendChild(main);
    div.appendChild(stats);
    div.appendChild(ops);

    div._ui = {
      input: input,
      highlight: highlight,
      msg: msg,
      expand: expand,
      expandSummary: expandSummary,
      expandCode: expandCode,
      stats: statEls,
    };
    return div;
  }

  function insertRowAfter(rowDiv, value) {
    const newRow = createRow(value);
    rowDiv.after(newRow);
    renumber();
    newRow._ui.input.focus();
    scheduleEvaluate();
  }

  function addRow(value) {
    const row = createRow(value == null ? "" : value);
    rowsEl.appendChild(row);
    renumber();
    return row;
  }

  function renumber() {
    Array.prototype.forEach.call(rowsEl.children, function (row, i) {
      row.querySelector(".row-no").textContent = i + 1;
    });
  }

  function collectState() {
    const start = Math.max(0, parseInt(startEl.value, 10) || 0);
    const rows = Array.prototype.map.call(
      rowsEl.querySelectorAll(".row-src"),
      function (input) {
        return input.value;
      }
    );
    return { start: start, rows: rows };
  }

  /* ---------------- 求值与渲染 ---------------- */

  let debounceTimer = null;
  function scheduleEvaluate() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(evaluate, 250);
  }

  let requestSeq = 0;
  async function evaluate() {
    const mySeq = ++requestSeq;
    const state = collectState();
    let data;
    try {
      const resp = await fetch("/api/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state),
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      data = await resp.json();
    } catch (e) {
      if (mySeq === requestSeq) {
        summaryEl.className = "summary show error";
        summaryEl.textContent = "评估请求失败：" + e.message;
      }
      return;
    }
    if (mySeq !== requestSeq) return; // 已有更新的请求，丢弃过期结果
    applyResults(data);
  }

  function applyResults(data) {
    const rowDivs = rowsEl.children;
    let errorCount = 0;
    let firstErrorRow = -1;
    let finalCount = data.start;
    let finalKnown = true;

    data.rows.forEach(function (r, i) {
      const div = rowDivs[i];
      if (!div) return;
      const ui = div._ui;
      div.classList.remove("ok", "error", "blocked", "empty");

      setStat(ui.stats.avail, r.available);
      setStat(ui.stats.cons, r.consumed);
      setStat(ui.stats.prod, r.produced);
      setStat(ui.stats.rem, r.remaining, r.remaining > 0);

      ui.highlight.hidden = true;
      ui.msg.hidden = true;
      ui.msg.classList.remove("neutral");
      ui.expand.hidden = true;

      if (r.status === "ok") {
        div.classList.add("ok");
        showExpansion(ui, r);
        finalCount = r.produced + r.remaining;
      } else if (r.status === "empty") {
        div.classList.add("empty");
        showMsg(ui, "空行：针数不变，直接传递到下一行", true);
      } else if (r.status === "blocked") {
        div.classList.add("blocked");
        showMsg(ui, "因前面的行出错，本行无法计算", true);
        finalKnown = false;
      } else if (r.status === "error") {
        div.classList.add("error");
        errorCount += 1;
        if (firstErrorRow < 0) firstErrorRow = i;
        if (r.error) {
          showMsg(ui, r.error.message, false);
          if (r.error.position) {
            showHighlight(ui, r.source, r.error.position);
          }
        }
        if (r.error && r.error.type === "unconsumed") {
          // 未消耗属于“可继续”的错误，针数仍可向后传递
          showExpansion(ui, r);
          finalCount = r.produced + r.remaining;
        } else {
          finalKnown = false;
        }
      }
    });

    renderSummary(data.rows.length, errorCount, firstErrorRow, finalCount, finalKnown);
  }

  function setStat(el, value, warn) {
    el.textContent = value == null ? "–" : value;
    el.classList.toggle("warn", !!warn);
  }

  function showMsg(ui, text, neutral) {
    ui.msg.textContent = text;
    ui.msg.hidden = false;
    ui.msg.classList.toggle("neutral", !!neutral);
  }

  function showExpansion(ui, r) {
    if (!r.expansionTotal) return;
    ui.expand.hidden = false;
    ui.expandSummary.textContent =
      "展开序列（共 " + r.expansionTotal + " 步" +
      (r.expansionTotal > r.expansion.length ? "，仅显示前 " + r.expansion.length + " 步" : "") +
      "）";
    ui.expandCode.textContent =
      r.expansion.join(" ") + (r.expansionTotal > r.expansion.length ? " …" : "");
  }

  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function showHighlight(ui, src, pos) {
    let start = Math.max(0, Math.min(pos.start, src.length));
    let end = Math.max(start, Math.min(pos.end, src.length));
    let html;
    if (start === end) {
      if (start < src.length) {
        end = start + 1; // 零宽位置：高亮该处字符
        html = escapeHtml(src.slice(0, start)) + "<mark>" + escapeHtml(src.slice(start, end)) + "</mark>" + escapeHtml(src.slice(end));
      } else {
        html = escapeHtml(src) + '<mark class="eof">▁</mark>'; // 行尾位置标记
      }
    } else {
      html = escapeHtml(src.slice(0, start)) + "<mark>" + escapeHtml(src.slice(start, end)) + "</mark>" + escapeHtml(src.slice(end));
    }
    ui.highlight.innerHTML = html;
    ui.highlight.hidden = false;
  }

  function renderSummary(total, errorCount, firstErrorRow, finalCount, finalKnown) {
    if (total === 0) {
      summaryEl.className = "summary";
      summaryEl.textContent = "";
      return;
    }
    summaryEl.className = "summary show " + (errorCount > 0 ? "error" : "ok");
    let text;
    if (errorCount > 0) {
      text = "✗ 共 " + total + " 行，第 " + (firstErrorRow + 1) + " 行起存在 " + errorCount + " 处问题";
    } else {
      text = "✓ 共 " + total + " 行，全部通过";
    }
    text += finalKnown ? "；最终针数 " + finalCount : "；最终针数未知（存在错误）";
    summaryEl.textContent = text;
  }

  /* ---------------- 导入 / 导出 ---------------- */

  function exportJSON() {
    const data = collectState();
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "knitting-plan.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  }

  function importJSON(file) {
    const reader = new FileReader();
    reader.onload = function () {
      try {
        const data = JSON.parse(reader.result);
        let start = 0;
        let rows = null;
        if (Array.isArray(data)) {
          rows = data; // 兼容直接导出为数组的情况
        } else if (data && typeof data === "object") {
          start = data.start;
          rows = data.rows;
        }
        if (!Number.isInteger(start) || start < 0) {
          throw new Error("start 必须是非负整数");
        }
        if (!Array.isArray(rows) || !rows.every(function (r) { return typeof r === "string"; })) {
          throw new Error("rows 必须是字符串数组");
        }
        startEl.value = start;
        rowsEl.innerHTML = "";
        rows.forEach(function (r) { addRow(r); });
        if (rows.length === 0) addRow("");
        renumber();
        evaluate();
      } catch (e) {
        alert("导入失败：" + e.message);
      }
    };
    reader.readAsText(file);
  }

  /* ---------------- 事件绑定与初始化 ---------------- */

  document.getElementById("addRowBtn").addEventListener("click", function () {
    const row = addRow("");
    row._ui.input.focus();
    scheduleEvaluate();
  });

  document.getElementById("exampleBtn").addEventListener("click", function () {
    startEl.value = EXAMPLE.start;
    rowsEl.innerHTML = "";
    EXAMPLE.rows.forEach(function (r) { addRow(r); });
    renumber();
    evaluate();
  });

  document.getElementById("clearBtn").addEventListener("click", function () {
    startEl.value = 0;
    rowsEl.innerHTML = "";
    addRow("");
    renumber();
    evaluate();
  });

  document.getElementById("exportBtn").addEventListener("click", exportJSON);

  document.getElementById("importBtn").addEventListener("click", function () {
    importFileEl.click();
  });
  importFileEl.addEventListener("change", function () {
    if (importFileEl.files && importFileEl.files[0]) {
      importJSON(importFileEl.files[0]);
    }
    importFileEl.value = "";
  });

  startEl.addEventListener("input", scheduleEvaluate);

  // 初始载入示例，便于直接看到效果
  startEl.value = EXAMPLE.start;
  EXAMPLE.rows.forEach(function (r) { addRow(r); });
  renumber();
  evaluate();
})();
