const $ = (id) => document.getElementById(id);

const state = {
  markdown: "",
};

function setStatus(text, mode = "") {
  const node = $("status");
  node.textContent = text;
  node.className = `status ${mode}`.trim();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

async function refreshHealth() {
  const response = await fetch("/api/health");
  const data = await response.json();
  const docs = data.documents || [];
  $("docs").innerHTML = docs.length
    ? docs
        .map(
          (doc) =>
            `<div class="item"><strong>${doc.title}</strong>${doc.course} · ${doc.chunk_count} 个片段</div>`,
        )
        .join("")
    : `<div class="item">知识库为空</div>`;
  setStatus("就绪");
}

function learnerPayload() {
  return {
    major: $("major").value,
    goal: $("goal").value,
    knowledge_level: $("level").value,
    learning_history: $("history").value,
    preferences: $("preferences").value,
    weak_points: $("weakPoints").value,
    available_time: $("availableTime").value,
  };
}

function selectedResourceTypes() {
  return [...document.querySelectorAll(".checks input:checked")].map((node) => node.value);
}

$("ingestBtn").addEventListener("click", async () => {
  try {
    setStatus("导入中", "busy");
    const data = await postJson("/api/ingest", {
      path: $("docPath").value,
      course: $("course").value,
      title: $("docTitle").value,
    });
    $("output").textContent = JSON.stringify(data.document, null, 2);
    await refreshHealth();
  } catch (error) {
    setStatus("出错", "error");
    $("output").textContent = error.message;
  }
});

$("searchBtn").addEventListener("click", async () => {
  try {
    setStatus("检索中", "busy");
    const data = await postJson("/api/search", {
      query: $("query").value,
      course: $("course").value,
      top_k: 5,
    });
    $("searchResults").innerHTML = data.results.length
      ? data.results
          .map(
            (item) =>
              `<div class="item"><strong>${item.title} ${item.page}</strong>${item.text.slice(0, 260)}</div>`,
          )
          .join("")
      : `<div class="item">未检索到相关片段</div>`;
    setStatus("就绪");
  } catch (error) {
    setStatus("出错", "error");
    $("searchResults").innerHTML = `<div class="item">${error.message}</div>`;
  }
});

$("generateBtn").addEventListener("click", async () => {
  try {
    setStatus("生成中", "busy");
    $("output").textContent = "多智能体协作生成中...";
    const data = await postJson("/api/generate", {
      course: $("course").value,
      learner: learnerPayload(),
      resource_types: selectedResourceTypes(),
      top_k: 6,
    });
    state.markdown = data.markdown;
    $("output").textContent = data.markdown;
    setStatus("就绪");
  } catch (error) {
    setStatus("出错", "error");
    $("output").textContent = error.message;
  }
});

$("copyBtn").addEventListener("click", async () => {
  await navigator.clipboard.writeText(state.markdown || $("output").textContent);
  setStatus("已复制");
});

refreshHealth().catch((error) => {
  setStatus("出错", "error");
  $("output").textContent = error.message;
});

