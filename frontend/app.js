// ---------------------------------------------------------------------------
// Element refs
// ---------------------------------------------------------------------------
const chatWindow = document.getElementById("chatWindow");
const form = document.getElementById("chatForm");
const input = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");
const attachImageBtn = document.getElementById("attachImageBtn");
const autoSpeakBtn = document.getElementById("autoSpeakBtn");
const imageInput = document.getElementById("imageInput");
const imageAttachPreview = document.getElementById("imageAttachPreview");
const imageAttachThumb = document.getElementById("imageAttachThumb");
const imageAttachName = document.getElementById("imageAttachName");
const imageAttachRemove = document.getElementById("imageAttachRemove");
const imageAttachStatus = document.getElementById("imageAttachStatus");
const fileAttachPreview = document.getElementById("fileAttachPreview");
const fileAttachName = document.getElementById("fileAttachName");
const fileAttachRemove = document.getElementById("fileAttachRemove");
const fileAttachStatus = document.getElementById("fileAttachStatus");
const textSnippetStatus = document.getElementById("textSnippetStatus");
const compactSuggestion = document.getElementById("compactSuggestion");
const compactBtn = document.getElementById("compactBtn");
const dismissCompactBtn = document.getElementById("dismissCompactBtn");
const compactError = document.getElementById("compactError");
const statusDot = document.getElementById("statusDot");
const hardwareLabel = document.getElementById("hardwareLabel");
const appVersion = document.getElementById("appVersion");
const ejectDot = document.getElementById("ejectDot");
const personaSelect = document.getElementById("personaSelect");
const helpBtn = document.getElementById("helpBtn");
const onboardingModal = document.getElementById("onboardingModal");
const onboardingIcon = document.getElementById("onboardingIcon");
const onboardingTitle = document.getElementById("onboardingTitle");
const onboardingBody = document.getElementById("onboardingBody");
const onboardingDots = document.getElementById("onboardingDots");
const onboardingBack = document.getElementById("onboardingBack");
const onboardingNext = document.getElementById("onboardingNext");
const onboardingSkip = document.getElementById("onboardingSkip");

const setupScreen = document.getElementById("setupScreen");
const modelChoices = document.getElementById("modelChoices");
const downloadProgress = document.getElementById("downloadProgress");
const downloadLabel = document.getElementById("downloadLabel");
const downloadFill = document.getElementById("downloadFill");
const downloadPct = document.getElementById("downloadPct");
const setupError = document.getElementById("setupError");

const newChatBtn = document.getElementById("newChatBtn");
const conversationList = document.getElementById("conversationList");
const uploadPdfBtn = document.getElementById("uploadPdfBtn");
const pdfInput = document.getElementById("pdfInput");
const docStatus = document.getElementById("docStatus");
const pdfProgress = document.getElementById("pdfProgress");
const pdfProgressFill = document.getElementById("pdfProgressFill");
const cancelUploadBtn = document.getElementById("cancelUploadBtn");
const pdfDropZone = document.getElementById("pdfDropZone");
const pdfQueueList = document.getElementById("pdfQueueList");
const manageCatsBtn = document.getElementById("manageCatsBtn");
const manageMemoryBtn = document.getElementById("manageMemoryBtn");
const memoryPanel = document.getElementById("memoryPanel");
const memoryModalClose = document.getElementById("memoryModalClose");
const memoryPanelList = document.getElementById("memoryPanelList");
const memoryAddInput = document.getElementById("memoryAddInput");
const memoryAddBtn = document.getElementById("memoryAddBtn");
const memoryError = document.getElementById("memoryError");
const catPanel = document.getElementById("catPanel");
const catModalClose = document.getElementById("catModalClose");
const catPanelList = document.getElementById("catPanelList");
const newCatInput = document.getElementById("newCatInput");
const addCatBtn = document.getElementById("addCatBtn");
const catError = document.getElementById("catError");
const manageAgentsBtn = document.getElementById("manageAgentsBtn");
const agentPanel = document.getElementById("agentPanel");
const agentModalClose = document.getElementById("agentModalClose");
const agentPanelList = document.getElementById("agentPanelList");
const newAgentName = document.getElementById("newAgentName");
const newAgentInstructions = document.getElementById("newAgentInstructions");
const newAgentCategories = document.getElementById("newAgentCategories");
const addAgentBtn = document.getElementById("addAgentBtn");
const agentError = document.getElementById("agentError");

const ejectStatus = document.getElementById("ejectStatus");
const sidebarEdgeToggle = document.getElementById("sidebarEdgeToggle");

const lockScreen = document.getElementById("lockScreen");
const unlockInput = document.getElementById("unlockInput");
const unlockBtn = document.getElementById("unlockBtn");
const unlockError = document.getElementById("unlockError");

const modelSelect = document.getElementById("modelSelect");
const removeModelBtn = document.getElementById("removeModelBtn");
const modelDropZone = document.getElementById("modelDropZone");
const modelInput = document.getElementById("modelInput");
const uploadModelBtn = document.getElementById("uploadModelBtn");
const modelUploadStatus = document.getElementById("modelUploadStatus");

const securityControls = document.getElementById("securityControls");
const manageBackupBtn = document.getElementById("manageBackupBtn");
const backupPanel = document.getElementById("backupPanel");
const backupModalClose = document.getElementById("backupModalClose");
const downloadBackupBtn = document.getElementById("downloadBackupBtn");
const restoreInput = document.getElementById("restoreInput");
const chooseRestoreBtn = document.getElementById("chooseRestoreBtn");
const restorePreview = document.getElementById("restorePreview");
const restoreSummary = document.getElementById("restoreSummary");
const confirmRestoreBtn = document.getElementById("confirmRestoreBtn");
const cancelRestoreBtn = document.getElementById("cancelRestoreBtn");
const backupError = document.getElementById("backupError");
const searchChatsBtn = document.getElementById("searchChatsBtn");
const searchPanel = document.getElementById("searchPanel");
const searchModalClose = document.getElementById("searchModalClose");
const chatSearchInput = document.getElementById("chatSearchInput");
const chatSearchResults = document.getElementById("chatSearchResults");
const layout = document.getElementById("layout");
const sidebar = document.getElementById("sidebar");

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let history = [];
let currentConvId = null;
let currentPersona = "default";
let pollTimer = null;
let isStreaming = false;
let currentAbortController = null;
let compactDismissed = false; // reset whenever the conversation changes — see newChatBtn/openConversation

// ---------------------------------------------------------------------------
// Setup / chat screen switching
// ---------------------------------------------------------------------------
function showChat() {
  setupScreen.classList.add("hidden");
  chatWindow.classList.remove("hidden");
  form.classList.remove("hidden");
}
function showSetup() {
  setupScreen.classList.remove("hidden");
  chatWindow.classList.add("hidden");
  form.classList.add("hidden");
}

// ---------------------------------------------------------------------------
// Tiny self-contained Markdown renderer (no CDN dependency, in keeping with
// the app being offline-first). Covers what a local LLM's responses
// actually use: headings, bold/italic, inline code, fenced code blocks,
// lists, and links. Always HTML-escapes first so nothing in the model's
// output can inject markup.
// ---------------------------------------------------------------------------
function escapeHtml(str) {
  // Quotes matter as much as angle brackets here. Escaped text gets
  // interpolated into attribute values further down (a markdown link's href
  // is built as href="${url}"), so leaving " and ' intact lets a crafted
  // link close the attribute early and add its own — e.g.
  //   [x](https://a" onmouseover="alert(1))
  // renders a live event handler with the angle brackets never involved.
  // That text isn't hypothetical: excerpts from an uploaded PDF reach the
  // model, and the model's reply is what gets rendered here.
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function inlineMarkdown(line) {
  // Pull inline code out first so its literal contents (backslashes,
  // asterisks, underscores — anything) can never be misread as bold/italic
  // markup, including across two separate `code` spans on the same line.
  const codeSpans = [];
  let out = line.replace(/`([^`]+)`/g, (_, content) => {
    const idx = codeSpans.length;
    codeSpans.push(`<code>${escapeHtml(content)}</code>`);
    return `\u0001CODE${idx}\u0001`;
  });

  out = escapeHtml(out);
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (whole, label, url) => {
    if (!/^https?:\/\//i.test(url)) return whole; // only linkify plain http(s) urls
    return `<a href="${url}" target="_blank" rel="noopener">${label}</a>`;
  });

  out = out.replace(/\u0001CODE(\d+)\u0001/g, (_, idx) => codeSpans[Number(idx)]);
  return out;
}

function renderMarkdown(text) {
  // Normalize line endings up front — a stray \r (from CRLF-saved content,
  // or text pasted from Windows sources) would otherwise get treated as
  // literal paragraph content instead of a line break.
  text = text.replace(/\r\n?/g, "\n");

  const rawBlocks = [];
  const codeBlocks = [];
  const withoutCode = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    const trimmed = code.trim();
    rawBlocks.push({ lang: lang || "", code: trimmed });
    if (lang && lang.toLowerCase() === "mermaid") {
      // Rendered into an actual diagram by renderMermaidDiagrams() right
      // after this HTML lands in the DOM — mermaid.render() needs a real
      // element to draw into, which doesn't exist yet at this point in
      // plain string-building. escapeHtml here is just so the raw source
      // survives as this div's HTML safely; mermaid reads it back via
      // .textContent, which un-escapes it again.
      codeBlocks.push(`<div class="mermaid">${escapeHtml(trimmed)}</div>`);
      return `\u0000CODEBLOCK${idx}\u0000`;
    }
    const cls = lang ? ` class="lang-${escapeHtml(lang)}"` : "";
    codeBlocks.push(
      `<div class="code-block-wrap">` +
      `<div class="code-block-bar"><span>${escapeHtml(lang || "text")}</span>` +
      `<button type="button" class="code-download-btn" data-block="${idx}">Download</button></div>` +
      `<pre><code${cls}>${escapeHtml(trimmed)}</code></pre></div>`
    );
    return `\u0000CODEBLOCK${idx}\u0000`;
  });

  let html = "";
  let listType = null; // 'ul' | 'ol' | null
  let paragraph = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      html += `<p>${paragraph.join(" ")}</p>`;
      paragraph = [];
    }
  };
  const closeList = () => {
    if (listType) { html += `</${listType}>`; listType = null; }
  };

  for (const line of withoutCode.split("\n")) {
    const trimmed = line.trim();
    const placeholderMatch = trimmed.match(/^\u0000CODEBLOCK(\d+)\u0000$/);
    const headerMatch = line.match(/^(#{1,4})\s+(.*)/);
    const ulMatch = line.match(/^[-*]\s+(.*)/);
    const olMatch = line.match(/^\d+\.\s+(.*)/);

    if (placeholderMatch) {
      flushParagraph(); closeList();
      html += codeBlocks[Number(placeholderMatch[1])];
    } else if (headerMatch) {
      flushParagraph(); closeList();
      const level = headerMatch[1].length + 2; // start at h3 so it fits inside a chat bubble
      html += `<h${level}>${inlineMarkdown(headerMatch[2])}</h${level}>`;
    } else if (ulMatch) {
      flushParagraph();
      if (listType !== "ul") { closeList(); html += "<ul>"; listType = "ul"; }
      html += `<li>${inlineMarkdown(ulMatch[1])}</li>`;
    } else if (olMatch) {
      flushParagraph();
      if (listType !== "ol") { closeList(); html += "<ol>"; listType = "ol"; }
      html += `<li>${inlineMarkdown(olMatch[1])}</li>`;
    } else if (trimmed === "") {
      flushParagraph(); closeList();
    } else {
      closeList();
      paragraph.push(inlineMarkdown(line));
    }
  }
  flushParagraph();
  closeList();
  return { html, blocks: rawBlocks };
}

// Raw (unescaped) code-block text per rendered message element, keyed by
// the element itself — populated by applyMarkdown(), read by the
// delegated download-button handler further down. A WeakMap rather than a
// plain object so entries for messages that get replaced (an aborted
// reply's bubble, an old turn's element after openConversation rebuilds
// the whole transcript) aren't kept alive forever.
const codeBlockRegistry = new WeakMap();

/** Renders markdown into `el` and records its code blocks for download —
 * every call site that used to do `el.innerHTML = renderMarkdown(text)`
 * uses this instead, so the registry can never drift out of sync with
 * what's actually on screen. */
function applyMarkdown(el, text) {
  const { html, blocks } = renderMarkdown(text);
  el.innerHTML = html;
  codeBlockRegistry.set(el, blocks);
  renderMermaidDiagrams(el);
}

// A top-level call into a global from another <script> tag is exactly the
// kind of thing that must never be allowed to throw here: this file is one
// script, executed top-to-bottom, and an uncaught error at this point would
// abort everything below it too — every dropdown population, event
// listener, and chat-bar setup later in this file, not just diagrams. If
// mermaid.min.js ever fails to load (a stale cached index.html from before
// it was added, a blocked request, a bad path — doesn't matter which), the
// rest of the app must still come up normally, just without diagrams.
if (typeof mermaid !== "undefined") {
  mermaid.initialize({ startOnLoad: false, theme: "default", securityLevel: "strict" });
}

/** Turns the ```mermaid fences renderMarkdown() already converted into
 * <div class="mermaid">source</div> placeholders into actual rendered
 * diagrams. Called after every applyMarkdown() — including the repeated
 * calls during token-by-token streaming, same as the rest of markdown
 * rendering already re-parses from scratch on every token, so this is
 * consistent with the existing performance tradeoff rather than a new one.
 * Each node gets a fresh random id since el.innerHTML is fully replaced on
 * every call, so there's never a stale rendered one still in the DOM to
 * skip via a "already processed" check. */
function renderMermaidDiagrams(el) {
  if (typeof mermaid === "undefined") return; // see the top-level guard above
  el.querySelectorAll(".mermaid").forEach(async (node) => {
    const source = node.textContent;
    try {
      const id = "mermaid-" + Math.random().toString(36).slice(2);
      const { svg } = await mermaid.render(id, source);
      node.innerHTML = svg;
    } catch {
      // Invalid or (mid-stream) incomplete diagram syntax — fall back to
      // the raw source as plain text rather than an error or empty box.
      node.outerHTML = `<pre><code>${escapeHtml(source)}</code></pre>`;
    }
  });
}

// Download button on every fenced code block in an assistant reply — not
// just ones that happen to follow a file attachment, since the AI writing
// out a snippet from scratch is just as worth saving as it rewriting an
// attached file. One delegated listener rather than one per button: blocks
// keep getting re-rendered (see the streaming loop above), which would
// otherwise mean re-attaching listeners on every token.
chatWindow.addEventListener("click", (e) => {
  const btn = e.target.closest(".code-download-btn");
  if (!btn) return;
  const msgEl = btn.closest(".msg");
  const blocks = msgEl && codeBlockRegistry.get(msgEl);
  const block = blocks && blocks[Number(btn.dataset.block)];
  if (!block) return;

  const ext = EXT_BY_LANG[block.lang.toLowerCase()] || (block.lang || "txt");
  const filename = `snippet-${Number(btn.dataset.block) + 1}.${ext}`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([block.code], { type: "text/plain" }));
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
});

function addMessage(role, text, imageDataUrl) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  if (role === "assistant") {
    applyMarkdown(el, text);
  } else {
    el.textContent = text;
  }
  if (imageDataUrl) {
    const img = document.createElement("img");
    img.src = imageDataUrl;
    img.className = "msg-image";
    img.alt = "Attached image";
    el.appendChild(img);
  }
  chatWindow.appendChild(el);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return el;
}

/** Shown in an assistant bubble from the moment a request is sent until its
 * first token arrives — document retrieval and, on the very first message,
 * loading the model into RAM can take a few seconds, and an empty bubble
 * during that gap reads as broken rather than working. */
/** "0.0s" under a minute, "1:23" once a reply (or a large model's first
 * load into RAM) runs past 60s — plain seconds would get hard to read once
 * digits climb into the tens on a slow CPU-only large model. */
function formatElapsedTime(ms) {
  const totalSeconds = ms / 1000;
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function showThinking(el) {
  el.classList.add("thinking");
  el.innerHTML =
    '<span class="thinking-dots"><span></span><span></span><span></span></span>' +
    '<span class="thinking-timer">0.0s</span>';
  const timerEl = el.querySelector(".thinking-timer");
  const start = performance.now();
  el._thinkingInterval = setInterval(() => {
    timerEl.textContent = formatElapsedTime(performance.now() - start);
  }, 100);
}

function hideThinking(el) {
  el.classList.remove("thinking");
  if (el._thinkingInterval) {
    clearInterval(el._thinkingInterval);
    el._thinkingInterval = null;
  }
  // The text-reply paths overwrite el's content entirely right after
  // calling this (applyMarkdown/textContent), so this is a no-op there —
  // but the image-generation paths only appendChild() an <img>, which
  // would otherwise leave the dots/timer sitting next to the finished
  // image forever.
  el.querySelector(".thinking-dots")?.remove();
  el.querySelector(".thinking-timer")?.remove();
}

// ---------------------------------------------------------------------------
// First-time introduction
//
// A short, skippable tour of the interface, shown once until dismissed
// (finishing the last step or clicking Skip both count), and reopenable any
// time from the ? button in the header. Tracked on the drive rather than in
// the browser's own storage — same reasoning as everywhere else in this
// app: the drive is the one source of truth, so the same drive picks up
// "already seen this" on a different PC too, same as it does for
// conversations and documents.
// ---------------------------------------------------------------------------
const ONBOARDING_STEPS = [
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-4 4v-4H6a2 2 0 0 1-2-2V5Z"></path></svg>',
    title: "Welcome to PocketMind",
    body: "This is a private AI assistant that runs entirely on this computer. Nothing you type is ever sent over the internet \u2014 everything happens right here, even without a connection.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"></path><path d="M22 2 15 22l-4-9-9-4 20-7Z"></path></svg>',
    title: "Just start typing",
    body: "Type a question or request in the box at the bottom of the screen and press Send. Want a different personality, or a different AI model? Use the dropdowns at the top of the screen any time \u2014 this drive comes with several models already installed, and you can add your own by dragging a .gguf file onto the Model section in the sidebar.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"></rect><path d="M5 11a7 7 0 0 0 14 0"></path><path d="M12 18v3"></path></svg>',
    title: "Talk, and listen back",
    body: "Click the mic to speak your question instead of typing it. To hear a reply instead of reading it, click the speaker icon under any response \u2014 or turn on the speaker toggle next to the mic to have every reply read aloud automatically.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15l-5-5L5 21"></path><rect x="3" y="3" width="18" height="18" rx="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle></svg>',
    title: "Show it a picture",
    body: "Click the image icon or drag a photo onto the message box to ask about it \u2014 describe a picture, read a screenshot, and so on. It switches to the \"Image Analysis\" model for you automatically if it isn't already active.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2"></path><circle cx="12" cy="12" r="2.5"></circle></svg>',
    title: "Create or edit a picture",
    body: "Just describe what you want \u2014 \"draw a lighthouse at sunset\" or \"generate a logo for...\" \u2014 and it's created right here with the on-device FLUX model. Attach a photo and describe a change instead (\"make the sky orange\") to edit that photo rather than starting from scratch.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"></path><path d="M14 2v6h6"></path></svg>',
    title: "Hand it a code file",
    body: "Drag a source file (.py, .js, .cs, and most other code/config types) onto the message box and ask the AI to review, explain, or rewrite it \u2014 the whole file rides along, including on follow-up questions. It switches to the Coding Helper persona automatically, a large file also switches to a more capable model, and any code the AI writes back has its own Download button.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="12" height="16" rx="1.5"></rect><path d="M7 8h6M7 12h6M7 16h3"></path><path d="M17 11v6M17 17l2.5-2.5M17 17l-2.5-2.5"></path></svg>',
    title: "Turn a reply into a document",
    body: "Ask for a Word document, spreadsheet, or PowerPoint deck and the reply comes with a matching download button \u2014 or one gets added automatically whenever a reply already looks like a document, table, or slide outline.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"></path></svg>',
    title: "Add your own documents",
    body: "Upload PDF, Word, Excel, or PowerPoint files from the sidebar and the assistant can reference them when answering \u2014 no need to mention them by name. Even a scanned or photographed PDF is read automatically. They're sorted into categories automatically, and you can drag a document to a different category any time.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h12a1 1 0 0 1 1 1v16l-7-4-7 4V4a1 1 0 0 1 1-1Z"></path></svg>',
    title: "Remember things for later",
    body: "Say something like \"remember that I'm allergic to penicillin\" and it'll bring that up automatically in later conversations. Review or delete anything it remembers from the Memory section in the sidebar.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="8" width="16" height="12" rx="2"></rect><circle cx="9" cy="14" r="1" fill="currentColor" stroke="none"></circle><circle cx="15" cy="14" r="1" fill="currentColor" stroke="none"></circle><path d="M12 8V4"></path><circle cx="12" cy="3" r="1"></circle></svg>',
    title: "Build a custom agent",
    body: "Create your own assistant from the Agents section in the sidebar \u2014 give it a name, instructions, and the document categories it should lean on. It shows up right alongside the built-in personas in the dropdown at the top.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"></path><path d="M7 10l5 5 5-5"></path><path d="M5 21h14"></path></svg>',
    title: "Save or print a conversation",
    body: "Click the \u2b07 next to any conversation title in the sidebar to download it as a text file \u2014 useful for printing, sharing, or keeping a copy outside the app.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="10.5" width="16" height="10" rx="2"></rect><path d="M7.5 10.5V7a4.5 4.5 0 0 1 9 0v3.5"></path></svg>',
    title: "Everything stays on this drive",
    body: "Your conversations and documents are saved right here, not in the cloud. The dot next to the hardware name in the top corner turns green once it's safe to unplug the drive. Want extra protection? Turn on a passphrase lock from the Security section in the sidebar.",
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M8 12.5l2.5 2.5 5.5-6"></path></svg>',
    title: "You're all set",
    body: "That's everything you need to get started. If you'd like to see this tour again, just click the ? button in the top corner.",
  },
];

let onboardingStep = 0;

function renderOnboardingStep() {
  const step = ONBOARDING_STEPS[onboardingStep];
  onboardingIcon.innerHTML = step.icon;
  onboardingTitle.textContent = step.title;
  onboardingBody.textContent = step.body;

  onboardingDots.innerHTML = "";
  ONBOARDING_STEPS.forEach((_, i) => {
    const dot = document.createElement("span");
    if (i === onboardingStep) dot.className = "active";
    onboardingDots.appendChild(dot);
  });

  // visibility (via a dedicated class), not the global .hidden — keeping
  // Back's space reserved on step 1 stops Next from jumping sideways to
  // recenter itself between steps.
  onboardingBack.classList.toggle("step-hidden", onboardingStep === 0);
  const isLast = onboardingStep === ONBOARDING_STEPS.length - 1;
  onboardingNext.textContent = isLast ? "Get started" : "Next";
}

function showOnboarding() {
  onboardingStep = 0;
  renderOnboardingStep();
  onboardingModal.classList.remove("hidden");
}

async function finishOnboarding() {
  onboardingModal.classList.add("hidden");
  try {
    await fetch("/api/onboarding-seen", { method: "POST" });
  } catch { /* non-critical — worst case it shows again next launch */ }
}

onboardingNext.addEventListener("click", () => {
  if (onboardingStep === ONBOARDING_STEPS.length - 1) {
    finishOnboarding();
  } else {
    onboardingStep++;
    renderOnboardingStep();
  }
});
onboardingBack.addEventListener("click", () => {
  if (onboardingStep > 0) {
    onboardingStep--;
    renderOnboardingStep();
  }
});
onboardingSkip.addEventListener("click", finishOnboarding);
helpBtn.addEventListener("click", showOnboarding);

async function checkStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.hardware) hardwareLabel.textContent = data.hardware.gpu_label;
    if (data.version) appVersion.textContent = data.version;
    updateEjectIndicator(data);
    renderSecurityControls(data.security);

    if (data.security && data.security.enabled && !data.security.unlocked) {
      lockScreen.classList.remove("hidden");
      layout.classList.add("hidden");
      return;  // don't load anything else until unlocked
    }
    lockScreen.classList.add("hidden");
    layout.classList.remove("hidden");

    if (data.ready) {
      statusDot.classList.add("ready");
      showChat();
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      newChatBtn.disabled = false;
      personaSelect.disabled = false;
      loadPersonas();
      loadConversations();
      loadDocuments();
      loadInstalledModels();
    } else {
      statusDot.classList.remove("ready");
      // The header/sidebar stay visible during setup, but New Chat and the
      // persona picker have nothing to act on yet - disable them instead of
      // leaving them looking clickable while silently doing nothing.
      newChatBtn.disabled = true;
      personaSelect.disabled = true;
      personaSelect.innerHTML = "";
      showSetup();
      loadCatalog();
    }
  } catch {
    hardwareLabel.textContent = "starting up…";
  }
}

function updateEjectIndicator(data) {
  ejectDot.classList.remove("safe", "unsafe");
  if (data.safe_to_eject) {
    ejectDot.classList.add("safe");
    ejectDot.title = "Safe to unplug the drive now — the AI model is fully loaded in memory.";
    ejectStatus.textContent = "✓ Safe to unplug now";
  } else {
    ejectDot.classList.add("unsafe");
    ejectDot.title = "Keep the drive connected — still loading, downloading, or installing.";
    ejectStatus.textContent = "Keep drive connected for now";
  }
}

// ---------------------------------------------------------------------------
// Sidebar collapse
//
// Deliberately not remembered between launches. Persisting it would mean
// writing to the host PC's browser storage, and "nothing touches the host
// machine" is a promise this app makes everywhere else — a cosmetic
// preference isn't worth being the one exception to it.
// ---------------------------------------------------------------------------
function setSidebarCollapsed(collapsed) {
  layout.classList.toggle("sidebar-collapsed", collapsed);
  const label = collapsed ? "Show sidebar (Ctrl+B)" : "Hide sidebar (Ctrl+B)";
  sidebarEdgeToggle.setAttribute("aria-expanded", String(!collapsed));
  sidebarEdgeToggle.title = label;
  // aria-hidden as well as pointer-events: the CSS stops a mouse reaching the
  // collapsed sidebar, but a screen reader would still walk straight into it.
  sidebar.setAttribute("aria-hidden", String(collapsed));
}

sidebarEdgeToggle.addEventListener("click", () => {
  setSidebarCollapsed(!layout.classList.contains("sidebar-collapsed"));
});

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "b") {
    e.preventDefault();
    setSidebarCollapsed(!layout.classList.contains("sidebar-collapsed"));
  }
  if (e.key === "Escape") {
    if (!agentPanel.classList.contains("hidden")) closeAgentModal();
    else if (!catPanel.classList.contains("hidden")) closeCatModal();
    else if (!memoryPanel.classList.contains("hidden")) closeMemoryModal();
    else if (!backupPanel.classList.contains("hidden")) closeBackupModal();
    else if (!searchPanel.classList.contains("hidden")) closeSearchModal();
  }
});

// ---------------------------------------------------------------------------
// Lock screen (encryption unlock)
// ---------------------------------------------------------------------------
unlockBtn.addEventListener("click", doUnlock);
unlockInput.addEventListener("keydown", (e) => { if (e.key === "Enter") doUnlock(); });

async function doUnlock() {
  const passphrase = unlockInput.value;
  if (!passphrase) return;
  unlockError.classList.add("hidden");
  unlockBtn.disabled = true;
  try {
    const res = await fetch("/api/security/unlock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passphrase }),
    });
    const data = await res.json();
    if (data.error) {
      unlockError.textContent = data.error;
      unlockError.classList.remove("hidden");
    } else {
      unlockInput.value = "";
      checkStatus();
    }
  } catch {
    unlockError.textContent = "Couldn't reach the app. Try again.";
    unlockError.classList.remove("hidden");
  }
  unlockBtn.disabled = false;
}

// ---------------------------------------------------------------------------
// Security controls (sidebar: set up / lock / turn off encryption)
// ---------------------------------------------------------------------------
function renderSecurityControls(security) {
  if (!security) return;
  securityControls.innerHTML = "";

  if (!security.enabled) {
    const btn = document.createElement("button");
    btn.textContent = "Lock this drive with a passphrase";
    btn.addEventListener("click", () => showSecurityForm("enable"));
    securityControls.appendChild(btn);
    return;
  }

  if (security.unlocked) {
    const lockBtn = document.createElement("button");
    lockBtn.textContent = "Lock now";
    lockBtn.addEventListener("click", async () => {
      lockBtn.disabled = true;
      try {
        const res = await fetch("/api/security/lock", { method: "POST" });
        const data = await res.json();
        if (data.error) {
          alert(data.error);
          lockBtn.disabled = false;
          return;
        }
      } catch {
        alert("Couldn't reach the app. Try again.");
        lockBtn.disabled = false;
        return;
      }
      checkStatus();
    });
    securityControls.appendChild(lockBtn);

    const disableBtn = document.createElement("button");
    disableBtn.textContent = "Turn off encryption";
    disableBtn.className = "danger-btn";
    disableBtn.addEventListener("click", () => showSecurityForm("disable"));
    securityControls.appendChild(disableBtn);
  }
}

function showSecurityForm(mode) {
  securityControls.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "security-form";

  const label = document.createElement("p");
  label.className = "sub-note";
  if (mode === "enable") {
    label.textContent = "Choose a passphrase. Conversations and documents will be encrypted. This can't be recovered if forgotten.";
  } else {
    label.textContent = "Enter your passphrase to turn encryption off and decrypt everything.";
  }
  wrap.appendChild(label);

  const pass1 = document.createElement("input");
  pass1.type = "password";
  pass1.placeholder = "Passphrase";
  wrap.appendChild(pass1);

  let pass2 = null;
  if (mode === "enable") {
    pass2 = document.createElement("input");
    pass2.type = "password";
    pass2.placeholder = "Confirm passphrase";
    wrap.appendChild(pass2);
  }

  const err = document.createElement("p");
  err.className = "error hidden";
  wrap.appendChild(err);

  const submitBtn = document.createElement("button");
  submitBtn.textContent = mode === "enable" ? "Turn on encryption" : "Turn off encryption";
  if (mode === "disable") submitBtn.className = "danger-btn";
  wrap.appendChild(submitBtn);

  const cancelBtn = document.createElement("button");
  cancelBtn.textContent = "Cancel";
  wrap.appendChild(cancelBtn);
  cancelBtn.addEventListener("click", checkStatus);

  submitBtn.addEventListener("click", async () => {
    err.classList.add("hidden");
    if (mode === "enable" && pass1.value !== pass2.value) {
      err.textContent = "Passphrases don't match.";
      err.classList.remove("hidden");
      return;
    }
    submitBtn.disabled = true;
    const endpoint = mode === "enable" ? "/api/security/enable" : "/api/security/disable";
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passphrase: pass1.value }),
      });
      const data = await res.json();
      if (data.error) {
        err.textContent = data.error;
        err.classList.remove("hidden");
        submitBtn.disabled = false;
        return;
      }
      checkStatus();
    } catch {
      err.textContent = "Couldn't reach the app. Try again.";
      err.classList.remove("hidden");
      submitBtn.disabled = false;
    }
  });

  securityControls.appendChild(wrap);
}

// ---------------------------------------------------------------------------
// Backup / restore — bundles conversations, custom agents, and the document
// library into one downloadable file, and can restore from one. A centered
// modal for the same reason as Categories/Agents: room to show what a
// selected backup actually contains before committing to something this
// destructive.
// ---------------------------------------------------------------------------
let pendingRestoreFile = null;

function openBackupModal() {
  backupPanel.classList.remove("hidden");
}
function closeBackupModal() {
  backupPanel.classList.add("hidden");
  resetRestorePicker();
}
manageBackupBtn.addEventListener("click", openBackupModal);
backupModalClose.addEventListener("click", closeBackupModal);
backupPanel.addEventListener("click", (e) => {
  if (e.target === backupPanel) closeBackupModal();
});

function showBackupError(msg) {
  backupError.textContent = msg;
  backupError.classList.toggle("hidden", !msg);
}

function resetRestorePicker() {
  pendingRestoreFile = null;
  restoreInput.value = "";
  restorePreview.classList.add("hidden");
  chooseRestoreBtn.classList.remove("hidden");
  showBackupError("");
}

downloadBackupBtn.addEventListener("click", () => {
  const a = document.createElement("a");
  a.href = "/api/backup";
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
});

chooseRestoreBtn.addEventListener("click", () => restoreInput.click());

restoreInput.addEventListener("change", async () => {
  const file = restoreInput.files[0];
  if (!file) return;
  showBackupError("");
  const form = new FormData();
  form.append("file", file);
  let data;
  try {
    const res = await fetch("/api/backup/inspect", { method: "POST", body: form });
    data = await res.json();
  } catch {
    showBackupError("Couldn't read that file. Try again.");
    restoreInput.value = "";
    return;
  }
  if (data.error) {
    showBackupError(data.error);
    restoreInput.value = "";
    return;
  }
  pendingRestoreFile = file;
  const { counts, created_at } = data.manifest;
  const when = created_at ? new Date(created_at).toLocaleString() : "an unknown time";
  restoreSummary.textContent =
    `This backup was made ${when} — ${counts.conversations} conversation${counts.conversations === 1 ? "" : "s"}, ` +
    `${counts.documents} document${counts.documents === 1 ? "" : "s"}, ${counts.categories} categor${counts.categories === 1 ? "y" : "ies"}. ` +
    `Restoring replaces everything currently here with this.`;
  chooseRestoreBtn.classList.add("hidden");
  restorePreview.classList.remove("hidden");
});

cancelRestoreBtn.addEventListener("click", resetRestorePicker);

confirmRestoreBtn.addEventListener("click", async () => {
  if (!pendingRestoreFile) return;
  if (!confirm(
    "This will permanently replace all conversations, custom agents, and documents on this drive " +
    "with what's in this backup. This can't be undone. Continue?"
  )) return;

  confirmRestoreBtn.disabled = true;
  showBackupError("");
  const form = new FormData();
  form.append("file", pendingRestoreFile);
  try {
    const res = await fetch("/api/backup/restore", { method: "POST", body: form });
    const data = await res.json();
    if (data.error) {
      showBackupError(data.error);
      confirmRestoreBtn.disabled = false;
      return;
    }
  } catch {
    showBackupError("Couldn't reach the app. Try again.");
    confirmRestoreBtn.disabled = false;
    return;
  }
  confirmRestoreBtn.disabled = false;
  closeBackupModal();
  // Everything on disk just changed out from under whatever's currently
  // shown — same treatment as a fresh load rather than trying to patch
  // each piece of UI state individually.
  currentConvId = null;
  history = [];
  chatWindow.innerHTML = "";
  loadConversations();
  loadDocuments();
  loadPersonas();
});

// ---------------------------------------------------------------------------
// Model setup / download (main chat model)
// ---------------------------------------------------------------------------
async function loadCatalog() {
  try {
    const res = await fetch("/api/models/catalog");
    const data = await res.json();
    if (data.download && data.download.active) { renderDownloading(data.download); return; }

    modelChoices.innerHTML = "";
    downloadProgress.classList.add("hidden");
    modelChoices.classList.remove("hidden");

    data.models.forEach((m) => {
      const card = document.createElement("div");
      card.className = "model-card" + (m.id === "balanced" ? " recommended" : "");
      card.innerHTML = `
        <div class="info">
          <div class="title">${m.label}</div>
          <div class="blurb">${m.blurb}</div>
          <div class="size">Download size: ~${m.size_gb} GB</div>
        </div>
        <button data-id="${m.id}">Install</button>
      `;
      card.querySelector("button").addEventListener("click", () => startDownload(m.id));
      modelChoices.appendChild(card);
    });
  } catch {
    setupError.textContent = "Couldn't load model options. Check your internet connection.";
    setupError.classList.remove("hidden");
  }
}

async function startDownload(modelId) {
  setupError.classList.add("hidden");
  try {
    const res = await fetch(`/api/models/download/${modelId}`, { method: "POST" });
    const data = await res.json();
    if (data.error) { setupError.textContent = data.error; setupError.classList.remove("hidden"); return; }
    modelChoices.classList.add("hidden");
    downloadProgress.classList.remove("hidden");
    pollTimer = setInterval(pollDownload, 800);
  } catch {
    setupError.textContent = "Couldn't start the download. Check your internet connection.";
    setupError.classList.remove("hidden");
  }
}

function renderDownloading(state) {
  modelChoices.classList.add("hidden");
  downloadProgress.classList.remove("hidden");
  const pct = state.total ? Math.round((state.progress / state.total) * 100) : 0;
  downloadLabel.textContent = `Installing ${state.filename || "model"}…`;
  downloadFill.style.width = pct + "%";
  downloadPct.textContent = pct + "%";
}

async function pollDownload() {
  try {
    const res = await fetch("/api/models/download-status");
    const state = await res.json();
    if (state.error) {
      clearInterval(pollTimer); pollTimer = null;
      setupError.textContent = state.error;
      setupError.classList.remove("hidden");
      downloadProgress.classList.add("hidden");
      modelChoices.classList.remove("hidden");
      return;
    }
    renderDownloading(state);
    if (!state.active && state.progress > 0) {
      clearInterval(pollTimer); pollTimer = null;
      downloadLabel.textContent = "Finishing up…";
      setTimeout(checkStatus, 1000);
    }
  } catch { /* transient — keep polling */ }
}

// ---------------------------------------------------------------------------
// Model switcher
// ---------------------------------------------------------------------------
// Tracks whether the currently active chat model can see images, so the
// attach-image control can guide users to switch models instead of letting
// them attach something the backend will just reject at send time.
let activeModelIsVision = false;
// "fast" / "balanced" / "quality" / "vision" for a base model, null for a
// custom one — lets attachImageFile()/attachCodeFile() pick a specific
// catalog model to auto-switch to (see switchToModel()).
let activeModelCatalogId = null;
let installedModelsByFilename = {};

async function loadInstalledModels() {
  try {
    const res = await fetch("/api/models/installed");
    const data = await res.json();
    modelSelect.innerHTML = "";
    installedModelsByFilename = {};
    data.models.forEach((m) => {
      installedModelsByFilename[m.filename] = m;
      const opt = document.createElement("option");
      opt.value = m.filename;
      opt.textContent = m.size_gb ? `${m.label} (${m.size_gb} GB)` : m.label;
      if (m.active) {
        opt.selected = true;
        activeModelIsVision = !!m.vision;
        activeModelCatalogId = m.catalog_id;
      }
      modelSelect.appendChild(opt);
    });
    updateRemoveModelBtn();
  } catch { /* non-critical */ }
}

/** Shows "Remove this model" only for a model the user installed themselves
 * (via drag-and-drop) — the models this drive ships with are always
 * switchable but never removable, so there's no button for them at all
 * rather than one that's present but disabled. */
function updateRemoveModelBtn() {
  const info = installedModelsByFilename[modelSelect.value];
  removeModelBtn.classList.toggle("hidden", !info || !info.removable);
}

/** Switches the active chat model, updating both the backend and every bit
 * of local state that tracks it (the dropdown, activeModelIsVision/
 * activeModelCatalogId, the Remove button). Shared by the dropdown's own
 * change handler and the automatic switches in attachImageFile()/
 * attachCodeFile() below, so there's exactly one place that does this. */
async function switchToModel(filename) {
  const info = installedModelsByFilename[filename];
  activeModelIsVision = !!(info && info.vision);
  activeModelCatalogId = info ? info.catalog_id : null;
  modelSelect.value = filename;
  updateRemoveModelBtn();
  modelSelect.disabled = true;
  try {
    const res = await fetch(`/api/models/select/${encodeURIComponent(filename)}`, { method: "POST" });
    const data = await res.json();
    modelSelect.disabled = false;
    return data.error ? { ok: false, error: data.error } : { ok: true };
  } catch {
    modelSelect.disabled = false;
    return { ok: false, error: "Couldn't switch models. Try again." };
  }
}

/** Finds an installed base model by its catalog id ("fast"/"balanced"/
 * "quality"/"vision") — every one of the four ships pre-installed and can
 * never be uninstalled (see delete_model()'s catalog check), so this is
 * always expected to find something. */
function findCatalogModel(catalogId) {
  return Object.values(installedModelsByFilename).find((m) => m.catalog_id === catalogId);
}

modelSelect.addEventListener("change", async () => {
  const result = await switchToModel(modelSelect.value);
  if (!result.ok) alert(result.error);
});

removeModelBtn.addEventListener("click", async () => {
  const filename = modelSelect.value;
  const info = installedModelsByFilename[filename];
  if (!info) return;
  if (!confirm(`Remove "${info.label}"? You installed this one yourself, so you'd need to install it again to use it later.`)) return;
  removeModelBtn.disabled = true;
  try {
    const r = await fetch(`/api/models/${encodeURIComponent(filename)}`, { method: "DELETE" });
    const d = await r.json();
    if (d.error) {
      alert(d.error);
    } else {
      loadInstalledModels();
    }
  } catch {
    alert("Couldn't reach the app. Try again.");
  }
  removeModelBtn.disabled = false;
});

// ---------------------------------------------------------------------------
// Memory: durable facts the user has asked to be remembered, surfaced back
// into every future conversation (see memory.py / fit_to_context's own
// docstring on the backend). Same modal treatment as Agents/Categories
// above — the sidebar itself just has a description and a button.
// ---------------------------------------------------------------------------
async function loadMemory() {
  if (memoryPanel.classList.contains("hidden")) return; // nothing visible to refresh
  try {
    const res = await fetch("/api/memory");
    const data = await res.json();
    memoryPanelList.innerHTML = "";
    if (data.error) {
      showMemoryError(data.error);
      return;
    }
    if (!data.entries.length) {
      const empty = document.createElement("p");
      empty.className = "sub-note";
      empty.textContent = "Nothing remembered yet.";
      memoryPanelList.appendChild(empty);
    }
    data.entries.forEach((entry) => {
      const row = document.createElement("div");
      row.className = "memory-item";
      const text = document.createElement("span");
      text.textContent = entry.text;
      const removeBtn = document.createElement("button");
      removeBtn.className = "memory-remove";
      removeBtn.title = "Forget this";
      removeBtn.textContent = "✕";
      removeBtn.addEventListener("click", async () => {
        await fetch(`/api/memory/${encodeURIComponent(entry.id)}`, { method: "DELETE" });
        loadMemory();
      });
      row.appendChild(text);
      row.appendChild(removeBtn);
      memoryPanelList.appendChild(row);
    });
  } catch { /* non-critical */ }
}

function showMemoryError(msg) {
  memoryError.textContent = msg;
  memoryError.classList.toggle("hidden", !msg);
}

async function addMemoryEntry() {
  const text = memoryAddInput.value.trim();
  if (!text) return;
  const res = await fetch("/api/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const out = await res.json().catch(() => ({}));
  if (out.error) { showMemoryError(out.error); return; }
  showMemoryError("");
  memoryAddInput.value = "";
  await loadMemory();
}
memoryAddBtn.addEventListener("click", addMemoryEntry);
memoryAddInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); addMemoryEntry(); }
});

async function openMemoryModal() {
  memoryPanel.classList.remove("hidden");
  showMemoryError("");
  await loadMemory();
}
function closeMemoryModal() {
  memoryPanel.classList.add("hidden");
}
manageMemoryBtn.addEventListener("click", openMemoryModal);
memoryModalClose.addEventListener("click", closeMemoryModal);
memoryPanel.addEventListener("click", (e) => {
  if (e.target === memoryPanel) closeMemoryModal();
});

// ---------------------------------------------------------------------------
// Bring-your-own model: drag a .gguf file onto the sidebar (or click to
// browse) to install a model that isn't in the curated catalog. Uses the
// same _download_state "busy" flag as the catalog installer/downloader on
// the backend, so the two can't collide, but doesn't share its polling UI —
// a local file copy doesn't need a progress bar the way an internet
// download does.
// ---------------------------------------------------------------------------
uploadModelBtn.addEventListener("click", () => modelInput.click());

modelInput.addEventListener("change", () => {
  if (modelInput.files.length > 0) uploadModelFile(modelInput.files[0]);
  modelInput.value = ""; // allow re-selecting the same file later
});

modelDropZone.addEventListener("dragover", (e) => {
  if (!e.dataTransfer || !e.dataTransfer.types || !e.dataTransfer.types.includes("Files")) return;
  e.preventDefault();
  modelDropZone.classList.add("drag-over");
});
modelDropZone.addEventListener("dragleave", (e) => {
  if (e.target === modelDropZone) modelDropZone.classList.remove("drag-over");
});
modelDropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  modelDropZone.classList.remove("drag-over");
  const files = e.dataTransfer && e.dataTransfer.files;
  if (!files || files.length === 0) return;
  if (files.length > 1) {
    showModelUploadStatus("Drop one .gguf file at a time.", true);
    return;
  }
  uploadModelFile(files[0]);
});

function showModelUploadStatus(text, isError) {
  modelUploadStatus.textContent = text;
  modelUploadStatus.classList.remove("hidden");
  modelUploadStatus.classList.toggle("error", !!isError);
}

async function uploadModelFile(file) {
  if (!file.name.toLowerCase().endsWith(".gguf")) {
    showModelUploadStatus(`"${file.name}" isn't a .gguf file — only .gguf models are supported.`, true);
    return;
  }
  uploadModelBtn.disabled = true;
  modelDropZone.classList.add("uploading");
  showModelUploadStatus(`Installing ${file.name}… this can take a while for large files.`, false);

  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch("/api/models/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (data.error) {
      showModelUploadStatus(data.error, true);
    } else {
      showModelUploadStatus(`Installed ${data.installed}.`, false);
      loadInstalledModels();
    }
  } catch {
    showModelUploadStatus("Couldn't reach the app to upload that file. Try again.", true);
  }
  uploadModelBtn.disabled = false;
  modelDropZone.classList.remove("uploading");
}

let customAgents = [];

async function loadPersonas() {
  try {
    const res = await fetch("/api/personas");
    const data = await res.json();
    let agentsData = [];
    try {
      const ares = await fetch("/api/agents");
      const adata = await ares.json();
      agentsData = adata.agents || [];
    } catch { agentsData = []; }
    customAgents = agentsData;

    // A remembered selection (currentPersona) has to survive this rebuild —
    // otherwise every refresh (e.g. after creating an unrelated category)
    // would silently snap the active assistant back to the first option.
    const previousValue = currentPersona;
    personaSelect.innerHTML = "";

    const presetGroup = document.createElement("optgroup");
    presetGroup.label = "Presets";
    data.personas.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.label;
      presetGroup.appendChild(opt);
    });
    personaSelect.appendChild(presetGroup);

    if (customAgents.length > 0) {
      const agentGroup = document.createElement("optgroup");
      agentGroup.label = "Custom Agents";
      customAgents.forEach((a) => {
        const opt = document.createElement("option");
        opt.value = a.id;
        opt.textContent = a.name;
        agentGroup.appendChild(opt);
      });
      personaSelect.appendChild(agentGroup);
    }

    const stillExists = [...personaSelect.options].some((o) => o.value === previousValue);
    personaSelect.value = stillExists ? previousValue : (data.personas[0]?.id || "");
    currentPersona = personaSelect.value;
  } catch { /* non-critical */ }
}
personaSelect.addEventListener("change", () => { currentPersona = personaSelect.value; });

// ---------------------------------------------------------------------------
// Custom agents panel — a centered modal (see #agentPanel/.modal-box-lg in
// index.html), same pattern as the categories modal just below and the
// onboarding tour. Used to be an inline reveal in the sidebar, but a wide
// agent list got hard to read and click precisely in a ~140px column.
// ---------------------------------------------------------------------------
async function openAgentModal() {
  agentPanel.classList.remove("hidden");
  await loadCategories();
  await renderAgentPanel();
}
function closeAgentModal() {
  agentPanel.classList.add("hidden");
}
manageAgentsBtn.addEventListener("click", openAgentModal);
agentModalClose.addEventListener("click", closeAgentModal);
// Backdrop click closes; a click inside .modal-box-lg itself must not
// bubble up and be mistaken for one on the backdrop (the modal box doesn't
// cover the full overlay, so a click landing outside it — but still
// inside #agentPanel — is genuinely the backdrop).
agentPanel.addEventListener("click", (e) => {
  if (e.target === agentPanel) closeAgentModal();
});

function showAgentError(msg) {
  agentError.textContent = msg;
  agentError.classList.toggle("hidden", !msg);
}

function renderCategoryCheckboxes(container, selectedIds) {
  container.innerHTML = "";
  if (categories.length === 0) {
    const empty = document.createElement("p");
    empty.className = "sub-note";
    empty.textContent = "Create a document category first (see Documents \u2192 Categories below).";
    container.appendChild(empty);
    return;
  }
  for (const c of categories) {
    const label = document.createElement("label");
    label.className = "agent-cat-check";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = c.id;
    box.checked = selectedIds.includes(c.id);
    const span = document.createElement("span");
    span.textContent = c.name;
    label.appendChild(box);
    label.appendChild(span);
    container.appendChild(label);
  }
}

async function renderAgentPanel() {
  const agents = await (async () => {
    try {
      const res = await fetch("/api/agents");
      const data = await res.json();
      customAgents = data.agents || [];
      return customAgents;
    } catch { return customAgents; }
  })();

  agentPanelList.innerHTML = "";
  if (agents.length === 0) {
    const empty = document.createElement("p");
    empty.className = "sub-note";
    empty.textContent = "No custom agents yet. Create one below.";
    agentPanelList.appendChild(empty);
  }

  for (const a of agents) {
    const row = document.createElement("div");
    row.className = "agent-row";

    const header = document.createElement("div");
    header.className = "agent-row-header";
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.value = a.name;
    nameInput.maxLength = 40;
    nameInput.className = "cat-rename";
    const commitName = async () => {
      const next = nameInput.value.trim();
      if (!next || next === a.name) { nameInput.value = a.name; return; }
      const res = await fetch(`/api/agents/${a.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: next }),
      });
      const out = await res.json().catch(() => ({}));
      if (out.error) { showAgentError(out.error); nameInput.value = a.name; return; }
      showAgentError("");
      await loadPersonas();
      await renderAgentPanel();
    };
    nameInput.addEventListener("blur", commitName);
    nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") nameInput.blur(); });

    const del = document.createElement("button");
    del.className = "cat-del";
    del.textContent = "✕";
    del.title = "Delete this agent";
    del.addEventListener("click", async () => {
      if (!confirm(`Delete the “${a.name}” agent? This can't be undone (its priority categories themselves are untouched).`)) return;
      const res = await fetch(`/api/agents/${a.id}`, { method: "DELETE" });
      const out = await res.json().catch(() => ({}));
      if (out.error) { showAgentError(out.error); return; }
      showAgentError("");
      await loadPersonas();
      await renderAgentPanel();
    });

    header.appendChild(nameInput);
    header.appendChild(del);
    row.appendChild(header);

    const catBox = document.createElement("div");
    catBox.className = "agent-cat-checks";
    renderCategoryCheckboxes(catBox, a.category_ids || []);
    catBox.addEventListener("change", async () => {
      const chosen = [...catBox.querySelectorAll("input:checked")].map((i) => i.value);
      if (chosen.length === 0) { showAgentError("Pick at least one category to prioritize."); return; }
      const res = await fetch(`/api/agents/${a.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category_ids: chosen }),
      });
      const out = await res.json().catch(() => ({}));
      if (out.error) { showAgentError(out.error); return; }
      showAgentError("");
    });
    row.appendChild(catBox);

    agentPanelList.appendChild(row);
  }

  renderCategoryCheckboxes(newAgentCategories, []);
}

async function createAgent() {
  const name = newAgentName.value.trim();
  const chosen = [...newAgentCategories.querySelectorAll("input:checked")].map((i) => i.value);
  if (!name) { showAgentError("Give the agent a name."); return; }
  if (chosen.length === 0) { showAgentError("Pick at least one category to prioritize."); return; }
  const res = await fetch("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, category_ids: chosen, instructions: newAgentInstructions.value }),
  });
  const out = await res.json().catch(() => ({}));
  if (out.error) { showAgentError(out.error); return; }
  showAgentError("");
  newAgentName.value = "";
  newAgentInstructions.value = "";
  await loadPersonas();
  await renderAgentPanel();
}
addAgentBtn.addEventListener("click", createAgent);
newAgentName.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); createAgent(); } });

// ---------------------------------------------------------------------------
// Saved conversations
// ---------------------------------------------------------------------------
async function loadConversations() {
  try {
    const res = await fetch("/api/conversations");
    const data = await res.json();
    conversationList.innerHTML = "";
    data.conversations.forEach((c) => {
      const item = document.createElement("div");
      item.className = "conv-item";
      // The title is the first 60 characters of the user's own first
      // message, so it can contain anything they typed or pasted. Building
      // the row's structure with innerHTML is fine; putting the title in
      // via textContent is what keeps `<img onerror=...>` in a message from
      // becoming a live element in the sidebar. Same reasoning as the PDF
      // filenames in the documents list.
      item.innerHTML = `<span class="title"></span><span class="export" title="Export">⬇</span><span class="del">✕</span>`;
      const titleEl = item.querySelector(".title");
      titleEl.textContent = c.title;
      titleEl.title = c.title;
      titleEl.addEventListener("click", () => openConversation(c.id));
      item.querySelector(".export").addEventListener("click", (e) => {
        e.stopPropagation();
        exportConversation(c.id);
      });
      item.querySelector(".del").addEventListener("click", async (e) => {
        e.stopPropagation();
        await fetch(`/api/conversations/${c.id}`, { method: "DELETE" });
        loadConversations();
      });
      conversationList.appendChild(item);
    });

    // Same pattern as the PDF upload queue's Clear button: a footer link
    // that only appears when there's something to act on. Unlike the
    // queue's Clear (which just dismisses a status display — the
    // documents themselves are untouched), this one deletes real saved
    // conversations, so it asks first and names exactly how many.
    if (data.conversations.length > 0) {
      const footer = document.createElement("div");
      footer.id = "conversationListFooter";
      const clearBtn = document.createElement("button");
      clearBtn.className = "link-btn";
      clearBtn.textContent = "Clear";
      clearBtn.title = "Delete all saved conversations";
      clearBtn.addEventListener("click", () => clearAllConversations(data.conversations));
      footer.appendChild(clearBtn);
      conversationList.appendChild(footer);
    }
  } catch { /* non-critical */ }
}

async function clearAllConversations(conversations) {
  const count = conversations.length;
  const label = count === 1 ? "1 saved conversation" : `all ${count} saved conversations`;
  if (!confirm(`Delete ${label}? This can't be undone.`)) return;
  try {
    await Promise.all(conversations.map((c) => fetch(`/api/conversations/${c.id}`, { method: "DELETE" })));
  } catch {
    alert("Couldn't reach the app. Some conversations may not have been deleted.");
  }
  // Reloading rather than just clearing the DOM locally: if any individual
  // delete failed for an unexpected reason, this shows exactly what's
  // actually left rather than claiming a clean sweep that didn't happen.
  loadConversations();
  // If the conversation just open in the chat window was among those
  // deleted, start fresh rather than leaving a "current" conversation that
  // no longer exists anywhere to save back to.
  if (currentConvId && conversations.some((c) => c.id === currentConvId)) {
    currentConvId = null;
    history = [];
    chatWindow.innerHTML = "";
  }
}

function exportConversation(id) {
  const a = document.createElement("a");
  a.href = `/api/conversations/${id}/export?format=md`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function openConversation(id, messageIndexToReveal) {
  try {
    const res = await fetch(`/api/conversations/${id}`);
    const data = await res.json();
    if (data.error) return;
    stopSpeaking();
    currentConvId = id;
    history = data.messages || [];
    chatWindow.innerHTML = "";
    history.forEach((m, i) => {
      // A user turn that carried a file attachment was saved with the
      // file's full text folded into its content (see the submit handler)
      // — redraw it as the clean question + chip it looked like when sent,
      // rather than dumping the marker and the whole file as if the user
      // had typed it.
      const fileMatch = m.role === "user" && m.content.match(FILE_ATTACHMENT_RE);
      if (fileMatch) {
        const el = addMessage("user", fileMatch[1]);
        addFileAttachNote(el, `${fileMatch[2]} (${fileMatch[3]})`);
        return;
      }
      const el = addMessage(m.role, m.content);
      if (m.role === "assistant" && m.content.trim()) {
        addMessageActions(el, m.content, precedingUserMessage(history, i));
      }
    });
    // chatWindow's children land in the same order as history, one per
    // entry, so the index a search result carries still lines up here —
    // used to jump straight to the message that matched instead of just
    // opening the conversation and leaving the reader to scroll for it.
    if (Number.isInteger(messageIndexToReveal) && chatWindow.children[messageIndexToReveal]) {
      const target = chatWindow.children[messageIndexToReveal];
      target.scrollIntoView({ block: "center" });
      target.classList.add("msg-highlight");
      setTimeout(() => target.classList.remove("msg-highlight"), 2000);
    }
    // A newly-opened conversation might already be long enough to suggest
    // compacting right away, and it's a different conversation than
    // whatever the suggestion was last dismissed for.
    compactDismissed = false;
    maybeSuggestCompact();
  } catch { /* non-critical */ }
}

async function saveCurrentConversation(titleOverride) {
  if (history.length === 0) return;
  // A file-attached turn's content is the question plus the file's full
  // text (see FILE_ATTACHMENT_RE) — strip that back down to just the
  // question before it becomes the sidebar title, same as it's stripped
  // back down before it's shown as a chat bubble. titleOverride exists for
  // compactConversation(): once compacting replaces history with the
  // synthetic summary exchange, deriving a title from THAT would rename the
  // conversation to "Please summarize our conversation so far..." instead
  // of keeping whatever it was actually about.
  const firstUserMsg = history.find((m) => m.role === "user")?.content || "";
  const fileMatch = firstUserMsg.match(FILE_ATTACHMENT_RE);
  const title = titleOverride || (fileMatch ? fileMatch[1] : firstUserMsg).slice(0, 60) || "Untitled chat";
  try {
    const res = await fetch("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: currentConvId, title, messages: history }),
    });
    const data = await res.json();
    currentConvId = data.id;
    loadConversations();
  } catch { /* non-critical */ }
}

// ---------------------------------------------------------------------------
// Compacting a long conversation — this app's own version of Claude Code's
// own /compact: summarizes everything said so far and replaces the growing
// history with that summary, rather than letting it grow without bound
// (fit_to_context in context_manager.py already trims the oldest turns
// silently once a request stops fitting the model's window — this is a
// deliberate, visible alternative to that, not a replacement for it).
// ---------------------------------------------------------------------------

// No client-side tokenizer to measure against, so this is a character-count
// heuristic rather than an exact budget check — chosen well under the
// model's real context ceiling (see context_manager.py's own budget math)
// so the suggestion shows up with room to act, not right as trimming starts.
const COMPACT_SUGGEST_THRESHOLD_CHARS = 10000;

function historyCharCount() {
  return history.reduce((sum, m) => sum + (m.content || "").length, 0);
}

function maybeSuggestCompact() {
  const shouldShow = !compactDismissed && !isStreaming && historyCharCount() > COMPACT_SUGGEST_THRESHOLD_CHARS;
  compactSuggestion.classList.toggle("hidden", !shouldShow);
}

dismissCompactBtn.addEventListener("click", () => {
  compactDismissed = true;
  compactSuggestion.classList.add("hidden");
});

compactBtn.addEventListener("click", async () => {
  compactBtn.disabled = true;
  compactBtn.textContent = "Compacting…";
  compactError.classList.add("hidden");
  // Captured before history gets replaced below — same title-deriving
  // logic saveCurrentConversation() normally does itself, computed here
  // instead so the conversation keeps its real title instead of being
  // renamed to the synthetic summary prompt (see saveCurrentConversation's
  // own titleOverride comment).
  const firstUserMsg = history.find((m) => m.role === "user")?.content || "";
  const fileMatch = firstUserMsg.match(FILE_ATTACHMENT_RE);
  const preservedTitle = (fileMatch ? fileMatch[1] : firstUserMsg).slice(0, 60) || "Untitled chat";
  try {
    const res = await fetch("/api/chat/compact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    });
    const data = await res.json();
    if (data.error) {
      compactError.textContent = data.error;
      compactError.classList.remove("hidden");
      return;
    }
    // Replaces the real history with a single synthetic exchange — a user
    // turn asking for the recap, and the model's own summary as its reply
    // — rather than one bare assistant message, since most chat templates
    // expect strict user/assistant alternation and this keeps that intact
    // for whatever comes next. Not rendered as literally as that in the
    // chat window itself (see below): a person re-reading the transcript
    // doesn't need to see the fake prompt that produced it, just that a
    // compaction happened and what it preserved.
    history = [
      { role: "user", content: "Please summarize our conversation so far so we can continue without losing context." },
      { role: "assistant", content: data.summary },
    ];
    chatWindow.innerHTML = "";
    addMessage("system", "— Conversation compacted —");
    const el = addMessage("assistant", data.summary);
    addMessageActions(el, data.summary, history[0].content);
    compactDismissed = false;
    compactSuggestion.classList.add("hidden");
    await saveCurrentConversation(preservedTitle);
  } catch {
    compactError.textContent = "Couldn't reach the app. Try again.";
    compactError.classList.remove("hidden");
  } finally {
    compactBtn.disabled = false;
    compactBtn.textContent = "Compact conversation";
  }
});

newChatBtn.addEventListener("click", () => {
  stopSpeaking();
  currentConvId = null;
  history = [];
  chatWindow.innerHTML = "";
  compactDismissed = false;
  compactSuggestion.classList.add("hidden");
  textSnippetStatus.classList.add("hidden");
  clearPendingImage();
  clearPendingFile();
});

// ---------------------------------------------------------------------------
// Chat search — a centered modal (same pattern as Categories/Agents/Backup)
// with a live-filtered list of matching messages across every saved
// conversation, each one a shortcut straight to where it was said.
// ---------------------------------------------------------------------------
let searchDebounceTimer = null;
let searchRequestId = 0;

function openSearchModal() {
  searchPanel.classList.remove("hidden");
  chatSearchInput.value = "";
  chatSearchResults.innerHTML = "";
  chatSearchInput.focus();
}
function closeSearchModal() {
  searchPanel.classList.add("hidden");
  clearTimeout(searchDebounceTimer);
}
searchChatsBtn.addEventListener("click", openSearchModal);
searchModalClose.addEventListener("click", closeSearchModal);
searchPanel.addEventListener("click", (e) => {
  if (e.target === searchPanel) closeSearchModal();
});

chatSearchInput.addEventListener("input", () => {
  clearTimeout(searchDebounceTimer);
  const q = chatSearchInput.value.trim();
  if (!q) {
    chatSearchResults.innerHTML = "";
    return;
  }
  // Debounced rather than firing on every keystroke — each search re-reads
  // every conversation file on the backend (see search_conversations'
  // docstring), which is fine per-call but wasteful fired that often.
  searchDebounceTimer = setTimeout(() => runChatSearch(q), 250);
});

async function runChatSearch(q) {
  const thisRequest = ++searchRequestId;
  let data;
  try {
    const res = await fetch(`/api/conversations/search?q=${encodeURIComponent(q)}`);
    data = await res.json();
  } catch {
    return;
  }
  // A slower earlier request landing after a faster later one would
  // otherwise flash stale results back onto the screen — only the most
  // recently issued search is allowed to render.
  if (thisRequest !== searchRequestId) return;

  const results = data.results || [];
  chatSearchResults.innerHTML = "";
  if (results.length === 0) {
    const empty = document.createElement("p");
    empty.className = "sub-note";
    empty.textContent = "No matches.";
    chatSearchResults.appendChild(empty);
    return;
  }

  for (const r of results) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "search-result";

    const title = document.createElement("span");
    title.className = "search-result-title";
    title.textContent = r.title;
    row.appendChild(title);

    if (r.snippet) {
      const snippet = document.createElement("span");
      snippet.className = "search-result-snippet";
      snippet.textContent = r.snippet;
      row.appendChild(snippet);
    }

    row.addEventListener("click", () => {
      closeSearchModal();
      openConversation(r.conversation_id, r.message_index);
    });
    chatSearchResults.appendChild(row);
  }
}

// ---------------------------------------------------------------------------
// Documents (PDF, Word, Excel, PowerPoint)
//
// Both the category list and the document library used to live in the
// sidebar, cramped into a narrow column. They're now merged into a single
// view inside the Categories modal: each category (plus a synthetic
// "Uncategorized" group for anything with no category, or whose category
// was deleted) renders as a collapsible header — rename/delete for real
// categories — followed by the documents filed under it. The sidebar keeps
// only the upload dropzone/queue/status; browsing and reassigning documents
// happens here.
// ---------------------------------------------------------------------------
let categories = [];
let allDocuments = [];
let collapsedCats = new Set();   // category ids the user has folded shut
let expandedDoc = null;          // document id whose move-control is showing

async function loadCategories() {
  try {
    const res = await fetch("/api/categories");
    const data = await res.json();
    categories = data.categories || [];
  } catch { categories = []; }
}

async function loadDocuments() {
  try {
    await loadCategories();
    const res = await fetch("/api/documents");
    const data = await res.json();
    allDocuments = data.documents || [];
    docStatus.textContent = data.embedding_model_ready
      ? ""
      : "First upload will install a small local reader (~100MB, one-time).";
    if (!catPanel.classList.contains("hidden")) renderCatPanel();
  } catch { /* non-critical */ }
}

let draggingDocId = null;

/** Shared by both reassignment paths (drag-and-drop and the explicit
 * picker) so there's exactly one place that calls the API, handles errors,
 * and refreshes the list. */
async function reassignDocumentCategory(docId, categoryId) {
  const res = await fetch(`/api/documents/${docId}/category`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category_id: categoryId || null }),
  });
  const out = await res.json().catch(() => ({}));
  if (out.error) { showCatError(out.error); return false; }
  expandedDoc = null;
  await loadDocuments();
  return true;
}

/** Toggles the category picker for a document and, if it just opened,
 * moves focus into it. renderCatPanel() tears down and rebuilds the whole
 * panel on every change, which would otherwise silently drop keyboard focus
 * back to <body> the moment someone activates the very button meant to be
 * the keyboard-accessible way to do this. */
function toggleDocPicker(docId) {
  const opening = expandedDoc !== docId;
  expandedDoc = opening ? docId : null;
  renderCatPanel();
  if (opening) {
    const select = catPanelList.querySelector(`.doc-cat-select[data-doc-id="${docId}"]`);
    if (select) select.focus();
  }
}

function buildDocRow(d) {
  const wrap = document.createElement("div");
  wrap.className = "doc-row";

  const item = document.createElement("div");
  item.className = "doc-item";
  const name = document.createElement("span");
  // textContent, not innerHTML: a document's filename is attacker-controlled in
  // the sense that it comes from whatever file was dropped in, and there's no
  // reason for it to be able to inject markup into the modal.
  name.textContent = d.filename;
  name.title = `${d.filename} — drag to another category, or click to move it`;
  name.className = "doc-name";
  name.draggable = true;
  name.addEventListener("click", () => toggleDocPicker(d.id));
  // Dragging is the primary way to move a document between categories; the
  // move icon and the click-to-reveal picker below are how a keyboard or
  // touch user reaches the same action, since native HTML5 drag-and-drop has
  // no keyboard equivalent and spotty touch support. dataTransfer is set for
  // browser compliance (Firefox in particular won't start a drag without it)
  // but isn't the actual source of truth — draggingDocId is, since it's
  // simpler and doesn't depend on dataTransfer's same-page read/write quirks
  // for something that never leaves this one list.
  name.addEventListener("dragstart", (e) => {
    draggingDocId = d.id;
    catPanelList.classList.add("dnd-active");
    item.classList.add("dragging");
    try {
      // Deliberately NOT text/plain for the id itself. Every editable text
      // field in this app (the chat box, category/agent rename inputs, the
      // "new category" field) has a browser-native built-in behavior:
      // dropping a text/plain payload onto it inserts that text verbatim,
      // before any of this app's own JS ever sees the drop. If the id were
      // text/plain, an accidental drop a few pixels off target would
      // silently paste a meaningless UUID into whatever the person was
      // typing. A custom MIME type has no such built-in handling, so an
      // off-target drop there does nothing instead. text/plain is still
      // set, just to the filename — something a person would actually
      // recognize if a drop does land in a text field, deliberately or not.
      e.dataTransfer.setData("application/x-pocketmind-doc-id", d.id);
      e.dataTransfer.setData("text/plain", d.filename);
      e.dataTransfer.effectAllowed = "move";
    } catch { /* fine without it — draggingDocId still carries the real state */ }
  });
  name.addEventListener("dragend", () => {
    draggingDocId = null;
    catPanelList.classList.remove("dnd-active");
    item.classList.remove("dragging");
    // Belt-and-suspenders: a drop target's own dragleave normally clears
    // this, but a drag that ends outside any valid target can leave a
    // highlight stuck if the pointer left the window entirely.
    catPanelList.querySelectorAll(".cat-group.drop-target").forEach((h) => h.classList.remove("drop-target"));
  });

  // <button>, not <span>: this is the keyboard/touch fallback to
  // drag-and-drop, so it needs to actually BE keyboard-operable — a span
  // with only a click listener isn't in the tab order and doesn't respond
  // to Enter/Space, which would make the "accessible fallback" not
  // accessible at all. A real button gets both of those natively.
  const move = document.createElement("button");
  move.type = "button";
  move.className = "move";
  move.title = "Move to a different category";
  move.setAttribute("aria-label", "Move to a different category");
  move.innerHTML =
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"></path></svg>';
  move.addEventListener("click", () => toggleDocPicker(d.id));

  const del = document.createElement("button");
  del.type = "button";
  del.className = "del";
  del.textContent = "✕";
  del.title = "Remove this document";
  del.setAttribute("aria-label", "Remove this document");
  del.addEventListener("click", async () => {
    // Every other destructive action in this app (category/agent/
    // conversation delete, removing an installed model) confirms first —
    // this one didn't, which made a single stray click permanently lose a
    // document with no warning at all. There's no raw file kept anywhere
    // to recover from either (see ingest_document in rag.py): once deleted,
    // re-uploading the original is the only way back.
    if (!confirm(`Delete "${d.filename}"? This can't be undone.`)) return;
    await fetch(`/api/documents/${d.id}`, { method: "DELETE" });
    loadDocuments();
  });
  item.appendChild(name);
  item.appendChild(move);
  item.appendChild(del);
  wrap.appendChild(item);

  if (expandedDoc === d.id) {
    const actions = document.createElement("div");
    actions.className = "doc-actions";
    const select = document.createElement("select");
    select.className = "doc-cat-select";
    select.dataset.docId = d.id;
    const none = document.createElement("option");
    none.value = "";
    none.textContent = "Uncategorized";
    select.appendChild(none);
    for (const c of categories) {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      select.appendChild(opt);
    }
    select.value = d.category_id || "";
    select.addEventListener("change", () => reassignDocumentCategory(d.id, select.value || null));
    actions.appendChild(select);
    wrap.appendChild(actions);
  }
  return wrap;
}

// ---------------------------------------------------------------------------
// Categories panel — the only place empty categories are visible, and the
// only place they can be renamed or removed. It also holds the entire
// document library now: each category (plus Uncategorized) is a collapsible
// group of the documents filed under it, with drag-and-drop or the picker
// button to move a document between groups. A centered modal for the same
// reason as the agents one above, just wider to fit both jobs comfortably.
// ---------------------------------------------------------------------------
async function openCatModal() {
  catPanel.classList.remove("hidden");
  await loadDocuments(); // gated internally to render into catPanelList since the modal is now open
}
function closeCatModal() {
  catPanel.classList.add("hidden");
}
manageCatsBtn.addEventListener("click", openCatModal);
catModalClose.addEventListener("click", closeCatModal);
catPanel.addEventListener("click", (e) => {
  if (e.target === catPanel) closeCatModal();
});

function showCatError(msg) {
  catError.textContent = msg;
  catError.classList.remove("cat-success");
  catError.classList.toggle("hidden", !msg);
}

// Success gets its own explicit, visible confirmation — not just the row
// quietly appearing in the list. Reuses the same paragraph as errors
// (they're mutually exclusive moments) but in an unmistakable positive
// color, and clears itself after a few seconds rather than lingering.
let catSuccessTimer = null;
function showCatSuccess(msg) {
  clearTimeout(catSuccessTimer);
  catError.textContent = msg;
  catError.classList.add("cat-success");
  catError.classList.remove("hidden");
  catSuccessTimer = setTimeout(() => {
    catError.classList.add("hidden");
    catError.classList.remove("cat-success");
  }, 3000);
}

function renderCatPanel() {
  catPanelList.innerHTML = "";
  const docs = allDocuments;
  const loose = docs.filter((d) => !d.category_id || !categories.some((c) => c.id === d.category_id));

  if (categories.length === 0 && docs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "sub-note";
    empty.textContent = "No categories yet. Add one below.";
    catPanelList.appendChild(empty);
    return;
  }

  const groups = categories.map((c) => ({
    id: c.id, name: c.name, count: c.count, docs: docs.filter((d) => d.category_id === c.id), real: true,
  }));
  // Uncategorized sorts last regardless of whether it's empty — it's a
  // holding area, not a real category, and is never renamable or removable.
  groups.push({ id: null, name: "Uncategorized", count: loose.length, docs: loose, real: false });

  for (const group of groups) {
    catPanelList.appendChild(buildCatGroup(group, docs));
  }
}

/** One collapsible group in the panel: a header (rename/delete for a real
 * category, a plain label for Uncategorized, and a document count either
 * way) followed by the documents filed under it. The header doubles as a
 * drop target for drag-and-drop reassignment. */
function buildCatGroup(group, allDocs) {
  const key = group.id || "__none__";
  const isEmpty = group.docs.length === 0;
  const collapsed = collapsedCats.has(key);

  const wrap = document.createElement("div");
  wrap.className = "cat-group-wrap";

  const header = document.createElement("div");
  header.className = "cat-group" + (collapsed ? " collapsed" : "");

  const caret = document.createElement("span");
  caret.className = "cat-caret";
  caret.textContent = collapsed ? "▸" : "▾";
  header.appendChild(caret);

  if (group.real) {
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.value = group.name;
    nameInput.maxLength = 40;
    nameInput.className = "cat-rename";
    // Typing/clicking into the rename field shouldn't also toggle the
    // group's collapsed state — the header's own click handler below would
    // otherwise fire on every click that lands in this input too.
    nameInput.addEventListener("click", (e) => e.stopPropagation());
    const commit = async () => {
      const next = nameInput.value.trim();
      if (!next || next === group.name) { nameInput.value = group.name; return; }
      const res = await fetch(`/api/categories/${group.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: next }),
      });
      const out = await res.json().catch(() => ({}));
      if (out.error) { showCatError(out.error); nameInput.value = group.name; return; }
      await loadDocuments();
      showCatSuccess(`Renamed to "${out.category.name}"`);
    };
    nameInput.addEventListener("blur", commit);
    nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") nameInput.blur(); });
    header.appendChild(nameInput);
  } else {
    const name = document.createElement("span");
    name.className = "cat-name";
    name.textContent = group.name;
    header.appendChild(name);
  }

  const count = document.createElement("span");
  count.className = "cat-count";
  count.textContent = group.count;
  header.appendChild(count);

  if (group.real) {
    const del = document.createElement("button");
    del.type = "button";
    del.className = "cat-del";
    del.textContent = "✕";
    del.title = group.count
      ? `Remove this category — its ${group.count} document${group.count > 1 ? "s" : ""} move to Uncategorized`
      : "Remove this category";
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      // Only worth a confirmation when something actually moves as a result.
      if (group.count > 0 && !confirm(
        `Remove “${group.name}”?\n\nIts ${group.count} document${group.count > 1 ? "s" : ""} will move to Uncategorized. ` +
        `The documents themselves are kept.`
      )) return;
      const res = await fetch(`/api/categories/${group.id}`, { method: "DELETE" });
      const out = await res.json().catch(() => ({}));
      if (out.error) { showCatError(out.error); return; }
      showCatError("");
      await loadDocuments();
    });
    header.appendChild(del);
  }

  header.addEventListener("click", () => {
    if (collapsed) collapsedCats.delete(key); else collapsedCats.add(key);
    renderCatPanel();
  });

  // Drop target: any category header, including Uncategorized and empty
  // ones revealed mid-drag. dragover must call preventDefault() — that's
  // the browser's own signal that this element accepts the drop; without
  // it, drop never fires here at all.
  header.addEventListener("dragover", (e) => {
    if (draggingDocId === null) return;
    e.preventDefault();
    header.classList.add("drop-target");
  });
  header.addEventListener("dragleave", () => header.classList.remove("drop-target"));
  header.addEventListener("drop", async (e) => {
    e.preventDefault();
    header.classList.remove("drop-target");
    if (draggingDocId === null) return;
    const droppedId = draggingDocId;
    const dropped = allDocs.find((d) => d.id === droppedId);
    if (dropped && dropped.category_id === group.id) return; // already there — no-op
    await reassignDocumentCategory(droppedId, group.id);
  });

  wrap.appendChild(header);
  if (!collapsed && !isEmpty) {
    for (const d of group.docs) {
      wrap.appendChild(buildDocRow(d));
    }
  }
  return wrap;
}

async function createCategory() {
  const name = newCatInput.value.trim();
  if (!name) return;
  const res = await fetch("/api/categories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const out = await res.json().catch(() => ({}));
  if (out.error) { showCatError(out.error); return; }
  newCatInput.value = "";
  await loadDocuments();
  showCatSuccess(`Created "${out.category.name}"`);
}

addCatBtn.addEventListener("click", createCategory);
newCatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); createCategory(); }
});

uploadPdfBtn.addEventListener("click", () => pdfInput.click());

pdfInput.addEventListener("change", () => {
  addFilesToQueue(pdfInput.files);
  pdfInput.value = ""; // allow re-selecting the same file later
});

pdfDropZone.addEventListener("dragover", (e) => {
  // Gated on an actual file drag, not just any drag — without this, dragging
  // a document between categories elsewhere in the sidebar would light this
  // zone up as if it were a valid target, when dropping here would silently
  // do nothing (the drop handler below already no-ops correctly on a
  // non-file drag; this just keeps the visual cue honest about it too).
  if (!e.dataTransfer || !e.dataTransfer.types || !e.dataTransfer.types.includes("Files")) return;
  e.preventDefault();
  pdfDropZone.classList.add("drag-over");
});
pdfDropZone.addEventListener("dragleave", (e) => {
  if (e.target === pdfDropZone) pdfDropZone.classList.remove("drag-over");
});
pdfDropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  pdfDropZone.classList.remove("drag-over");
  if (e.dataTransfer && e.dataTransfer.files) addFilesToQueue(e.dataTransfer.files);
});

// ---------------------------------------------------------------------------
// Upload queue: multiple PDFs (picked at once, or dropped at once) are
// ingested one at a time — sequentially, not in parallel, since embedding
// is CPU-bound and running several at once would just fight over the same
// cores while making the existing single active-upload progress/cancel
// machinery ambiguous about which file it refers to.
// ---------------------------------------------------------------------------
let uploadQueue = []; // { id, file, status: 'pending'|'active'|'done'|'error'|'cancelled', message }
let queueProcessing = false;
let queueIdCounter = 0;

// Shared with the chat bar's own file drop (see DOCUMENT_FILE_EXTENSIONS'
// other use, further down near attachDocumentFile) — every extension
// extract_document_text() in rag.py knows how to read.
const DOCUMENT_FILE_EXTENSIONS = new Set(["pdf", "docx", "xlsx", "pptx"]);

function isDocumentFile(file) {
  return DOCUMENT_FILE_EXTENSIONS.has(fileExt(file.name));
}

function addFilesToQueue(fileList) {
  const incoming = Array.from(fileList || []);
  const docs = incoming.filter(isDocumentFile);
  const skipped = incoming.length - docs.length;

  for (const file of docs) {
    uploadQueue.push({ id: ++queueIdCounter, file, status: "pending", message: "" });
  }
  if (skipped > 0) {
    docStatus.textContent = `Skipped ${skipped} file${skipped > 1 ? "s" : ""} — only PDF, Word, Excel, and PowerPoint files are supported.`;
  }
  renderQueue();
  if (docs.length > 0) processQueue();
}

function renderQueue() {
  if (uploadQueue.length === 0) {
    pdfQueueList.classList.add("hidden");
    pdfQueueList.innerHTML = "";
    return;
  }
  pdfQueueList.classList.remove("hidden");
  pdfQueueList.innerHTML = "";

  const statusLabel = { pending: "Queued", active: "Reading…", done: "✓ Added", error: "✕ Failed",
                        cancelled: "Cancelled", duplicate: "Already have it" };

  for (const item of uploadQueue) {
    const row = document.createElement("div");
    row.className = `queue-item ${item.status}`;
    const name = document.createElement("span");
    name.className = "queue-name";
    name.textContent = item.file.name;
    name.title = item.message ? `${item.file.name} — ${item.message}` : item.file.name;
    row.appendChild(name);

    if (item.status === "pending") {
      const remove = document.createElement("button");
      remove.className = "queue-remove";
      remove.textContent = "✕";
      remove.title = "Remove from queue";
      remove.addEventListener("click", () => {
        uploadQueue = uploadQueue.filter((q) => q.id !== item.id);
        renderQueue();
      });
      row.appendChild(remove);
    } else {
      const status = document.createElement("span");
      status.className = "queue-status";
      status.textContent =
        item.status === "done" && item.message ? `✓ ${item.message}` :
        item.status === "duplicate" ? `⚠ ${item.message || statusLabel.duplicate}` :
        (statusLabel[item.status] || item.status);
      row.appendChild(status);
    }
    pdfQueueList.appendChild(row);
  }

  const settled = uploadQueue.every((q) =>
    q.status === "done" || q.status === "error" || q.status === "cancelled" || q.status === "duplicate");
  if (settled) {
    const footer = document.createElement("div");
    footer.id = "pdfQueueFooter";
    const clearBtn = document.createElement("button");
    clearBtn.className = "link-btn";
    clearBtn.textContent = "Clear";
    clearBtn.addEventListener("click", () => {
      uploadQueue = [];
      renderQueue();
    });
    footer.appendChild(clearBtn);
    pdfQueueList.appendChild(footer);
  }
}

async function processQueue() {
  if (queueProcessing) return;
  queueProcessing = true;

  // Make sure the local document-reading model is installed before
  // starting the queue, rather than re-checking before every file.
  docStatus.textContent = "Getting ready…";
  const statusRes = await fetch("/api/documents");
  const statusData = await statusRes.json();
  if (!statusData.embedding_model_ready) {
    docStatus.textContent = "Installing document reader (one-time, ~100MB)…";
    const installRes = await fetch("/api/documents/install-reader", { method: "POST" });
    const installData = await installRes.json();
    if (installData.error) {
      docStatus.textContent = installData.error;
      for (const item of uploadQueue) {
        if (item.status === "pending") { item.status = "error"; item.message = installData.error; }
      }
      renderQueue();
      queueProcessing = false;
      return;
    }
    const gotIt = await waitForEmbeddingModel();
    if (!gotIt) {
      const msg = "Document reader install is taking a while — try uploading again in a moment.";
      docStatus.textContent = msg;
      for (const item of uploadQueue) {
        if (item.status === "pending") { item.status = "error"; item.message = msg; }
      }
      renderQueue();
      queueProcessing = false;
      return;
    }
  }

  let next;
  while ((next = uploadQueue.find((q) => q.status === "pending"))) {
    next.status = "active";
    renderQueue();
    const result = await uploadOneFile(next.file);
    next.status = result.status;
    next.message = result.message || "";
    renderQueue();
    if (result.status === "done") loadDocuments();
  }

  queueProcessing = false;
  const doneCount = uploadQueue.filter((q) => q.status === "done").length;
  const dupCount = uploadQueue.filter((q) => q.status === "duplicate").length;
  if (doneCount > 0 || dupCount > 0) {
    const allAccountedFor = uploadQueue.every((q) => q.status === "done" || q.status === "duplicate");
    if (allAccountedFor && dupCount === 0) {
      docStatus.textContent = "All documents are ready to reference.";
    } else if (allAccountedFor && doneCount === 0) {
      docStatus.textContent = "Already in your library — nothing new to add.";
    } else if (allAccountedFor) {
      docStatus.textContent = `Added ${doneCount} new document${doneCount > 1 ? "s" : ""} — ` +
        `${dupCount} you already had.`;
    } else {
      docStatus.textContent = "Finished — see the list above for any that didn't make it.";
    }
  }
}

/** Uploads a single file through the existing progress/cancel machinery.
 * Returns { status: 'done' | 'error' | 'cancelled', message }. */
async function uploadOneFile(file) {
  docStatus.textContent = `Reading ${file.name}…`;
  pdfProgress.classList.remove("hidden");
  pdfProgressFill.style.width = "0%";
  // uploadPdfBtn is deliberately left enabled here. Its only job is to open
  // the file picker and add to uploadQueue — it doesn't touch the single
  // active-ingest slot that pdfProgress/cancelUploadBtn represent, so there's
  // no correctness reason to block it. Files picked while one is already
  // ingesting just join the queue and wait their turn (processQueue's
  // `while` loop below picks them up automatically once the current one
  // finishes), same as dragging more files onto the drop zone already did.
  cancelUploadBtn.disabled = false;
  cancelUploadBtn.textContent = "Cancel current";

  let cancelling = false;
  const onCancelClick = async () => {
    if (cancelling) return;
    cancelling = true;
    cancelUploadBtn.disabled = true;
    cancelUploadBtn.textContent = "Cancelling…";
    docStatus.textContent = `Cancelling ${file.name}…`;
    try {
      await fetch("/api/documents/cancel-upload", { method: "POST" });
    } catch { /* the upload request below will still resolve either way */ }
  };
  cancelUploadBtn.addEventListener("click", onCancelClick);

  const progressTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/documents/upload-status");
      const state = await res.json();
      if (state.active && state.total_chunks > 0 && !cancelling) {
        const pct = Math.round((state.chunks_done / state.total_chunks) * 100);
        pdfProgressFill.style.width = pct + "%";
        docStatus.textContent = `Reading ${file.name}… (${state.chunks_done}/${state.total_chunks} sections, ${pct}%)`;
      }
    } catch { /* transient — keep polling */ }
  }, 500);

  const formData = new FormData();
  formData.append("file", file);
  let outcome;
  try {
    const res = await fetch("/api/documents/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (data.cancelled) {
      docStatus.textContent = `Cancelled — ${file.name} was not added.`;
      outcome = { status: "cancelled", message: "Cancelled" };
    } else if (data.duplicate) {
      const msg = data.existing_filename && data.existing_filename !== file.name
        ? `You already have this — same content as "${data.existing_filename}".`
        : "You already have this document.";
      docStatus.textContent = `${file.name}: ${msg}`;
      outcome = { status: "duplicate", message: msg };
    } else if (data.error) {
      docStatus.textContent = data.error;
      outcome = { status: "error", message: data.error };
    } else {
      // Showing where it landed is what makes automatic filing safe to do at
      // all — a silent guess the user never sees is one they can never correct.
      const filed = data.category && data.category.name;
      docStatus.textContent = filed
        ? `${file.name} is ready — filed under ${data.category.name}. Click it above to move it.`
        : `${file.name} is ready to reference.`;
      outcome = { status: "done", message: filed ? `Filed under ${data.category.name}` : "" };
    }
  } catch {
    docStatus.textContent = "Couldn't upload that file. Try again.";
    outcome = { status: "error", message: "Couldn't reach the app." };
  } finally {
    clearInterval(progressTimer);
    cancelUploadBtn.removeEventListener("click", onCancelClick);
    pdfProgress.classList.add("hidden");
  }
  return outcome;
}

async function waitForEmbeddingModel() {
  for (let i = 0; i < 300; i++) {
    const res = await fetch("/api/documents");
    const data = await res.json();
    if (data.embedding_model_ready) return true;
    if (data.embedding_download && data.embedding_download.error) return false;
    await new Promise((r) => setTimeout(r, 1500));
  }
  return false;
}


// ---------------------------------------------------------------------------
// Image attachment — only meaningful for a vision-capable model, hence the
// activeModelIsVision guard before ever reading the file. Kept as a single
// pending attachment for the *next* message only, not stored in `history`
// (see the backend's /api/chat, which takes it as a separate top-level
// field for exactly this reason) — a multi-turn "remember this image"
// conversation isn't something this model class is built for anyway.
// ---------------------------------------------------------------------------
let pendingImage = null;

function showImageAttachError(text) {
  imageAttachStatus.textContent = text;
  imageAttachStatus.classList.remove("hidden");
  imageAttachStatus.classList.add("error");
}

function showImageAttachInfo(text) {
  imageAttachStatus.textContent = text;
  imageAttachStatus.classList.remove("hidden", "error");
}

function clearPendingImage() {
  pendingImage = null;
  imageAttachPreview.classList.add("hidden");
  imageAttachThumb.src = "";
  imageAttachName.textContent = "";
  imageAttachStatus.classList.add("hidden");
}

// This limit and the always-re-encode-through-canvas approach below were
// both driven by two real, undocumented failure modes measured directly
// against the vision model this app originally shipped with (Qwen2.5-VL,
// via llama-cpp-python's mtmd support): an oversized image (a plain
// 1920x1080 screenshot, unscaled, produces ~2700 image patches) could burn
// CPU for 5+ minutes with no error and no result rather than failing
// cleanly, and WebP threw "Failed to create bitmap from image bytes"
// outright since that decoder only handled what it was built against
// (JPEG/PNG).
//
// The model has since changed to MiniCPM-V 2.6 (see MODEL_CATALOG's
// "vision" entry in server.py for why) — a different vision encoder with
// its own, not-yet-separately-measured limits. Keeping this same
// conservative downscale+re-encode as a safe default rather than assuming
// it's still needed at these exact numbers, or that it's no longer needed
// at all: it costs little (one canvas pass) and re-encoding through canvas
// is a reasonable safety net for any vision model, not just the one that
// originally justified it. Worth re-measuring MiniCPM-V 2.6's own actual
// limits directly rather than trusting this comment's old numbers for it.
const MAX_IMAGE_DIMENSION = 896;

/** Returns a data URL for `file`, always re-encoded through canvas —
 * downscaled to fit within MAX_IMAGE_DIMENSION on its longest side if
 * needed (never upscaled), and normalized to a format the vision decoder
 * actually supports regardless of what it started as (see
 * MAX_IMAGE_DIMENSION's comment). Throws if that fails for any reason;
 * deliberately does NOT fall back to sending the file as-is, since an
 * unprocessed image is the one thing this function exists to prevent. The
 * caller shows a thrown error as an attach error instead. */
async function readImageForModel(file) {
  const bitmap = await createImageBitmap(file);
  const { width, height } = bitmap;
  const scale = Math.min(1, MAX_IMAGE_DIMENSION / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  // PNG stays PNG (screenshots/text benefit from staying lossless);
  // everything else (including formats the decoder can't read at all,
  // like WebP) becomes JPEG.
  const outType = file.type === "image/png" ? "image/png" : "image/jpeg";
  return canvas.toDataURL(outType, 0.9);
}

async function attachImageFile(file) {
  imageAttachStatus.classList.add("hidden");
  if (!file.type.startsWith("image/")) {
    showImageAttachError(`"${file.name}" isn't an image file.`);
    return;
  }
  // Attaching a photo implies wanting it looked at, so switch to the one
  // model that actually can rather than making the user do it themselves
  // first (or worse, silently sending it to a model that can't see it).
  // The vision model always ships pre-installed (findCatalogModel() can't
  // come back empty), so this has no "not installed" fallback to handle.
  if (!activeModelIsVision) {
    const vision = findCatalogModel("vision");
    const result = await switchToModel(vision.filename);
    if (!result.ok) { showImageAttachError(result.error); return; }
    showImageAttachInfo(`Switched to "${vision.label}" to read this photo.`);
  }
  try {
    pendingImage = await readImageForModel(file);
    imageAttachThumb.src = pendingImage;
    imageAttachName.textContent = file.name;
    imageAttachPreview.classList.remove("hidden");
  } catch {
    showImageAttachError(`Couldn't read "${file.name}".`);
  }
}

attachImageBtn.addEventListener("click", () => imageInput.click());

imageInput.addEventListener("change", () => {
  if (imageInput.files.length > 0) attachImageFile(imageInput.files[0]);
  imageInput.value = "";
});

imageAttachRemove.addEventListener("click", clearPendingImage);

// ---------------------------------------------------------------------------
// Code/program file attachment — drop a source file onto the chat bar and
// its FULL contents ride along with your next message, so the model can
// review or rewrite it. Deliberately not run through the RAG pipeline that
// paste-text/PDFs use: that chunks a document and retrieves only the
// top-matching snippets per question, which is right for a log or a manual
// but wrong for code — editing needs to see the whole file, not fuzzy
// fragments of it. The tradeoff is the flip side of that: unlike an image
// (used once, for one turn — see pendingImage above) or a pasted snippet
// (chunked once, then just searched), the attached file's full text is
// folded directly into `history` when sent, so it rides along on every
// later turn too. That's what makes "now fix the bug on line 40" work as a
// follow-up, but it also means it keeps costing context for the rest of
// the conversation — start a new chat to free that back up.
// ---------------------------------------------------------------------------
const CODE_FILE_EXTENSIONS = new Set([
  "py", "js", "jsx", "mjs", "cjs", "ts", "tsx", "java", "kt", "kts", "swift",
  "c", "h", "cpp", "cc", "cxx", "hpp", "cs", "go", "rs", "rb", "php", "pl",
  "lua", "dart", "scala", "r", "m", "sh", "bash", "zsh", "ps1", "bat", "cmd",
  "sql", "html", "htm", "css", "scss", "less", "vue", "svelte", "json",
  "yaml", "yml", "toml", "xml", "ini", "cfg", "gradle", "makefile", "dockerfile",
]);

// Maps a file extension to the language tag markdown fences use (and back
// again, for guessing a download filename from a code block — see the
// chatWindow click handler below applyMarkdown()).
const LANG_BY_EXT = {
  py: "python", js: "javascript", jsx: "jsx", mjs: "javascript", cjs: "javascript",
  ts: "typescript", tsx: "tsx", java: "java", kt: "kotlin", kts: "kotlin",
  swift: "swift", c: "c", h: "c", cpp: "cpp", cc: "cpp", cxx: "cpp", hpp: "cpp",
  cs: "csharp", go: "go", rs: "rust", rb: "ruby", php: "php", pl: "perl",
  lua: "lua", dart: "dart", scala: "scala", r: "r", m: "matlab",
  sh: "bash", bash: "bash", zsh: "bash", ps1: "powershell", bat: "batch", cmd: "batch",
  sql: "sql", html: "html", htm: "html", css: "css", scss: "scss", less: "less",
  vue: "vue", svelte: "svelte", json: "json", yaml: "yaml", yml: "yaml",
  toml: "toml", xml: "xml", ini: "ini",
};
const EXT_BY_LANG = Object.fromEntries(Object.entries(LANG_BY_EXT).map(([ext, lang]) => [lang, ext]));

function fileExt(filename) {
  const i = filename.lastIndexOf(".");
  return i === -1 ? "" : filename.slice(i + 1).toLowerCase();
}

/** Matches the marker a file-attached user message is built with (see the
 * submit handler) — group 1 is the typed question, group 2 the filename,
 * group 3 the line-count description. Used to redraw a clean bubble +
 * chip when a saved conversation is reopened, instead of dumping the raw
 * marker and the whole file's text into the transcript as if the user had
 * typed it. */
const FILE_ATTACHMENT_RE = /^([\s\S]*?)\n\n\[Attached file: (.+?) \((.+?)\)\]\n```[^\n]*\n[\s\S]*```$/;

function fileLineInfo(fileInfo) {
  return fileInfo.truncated
    ? `first ${fileInfo.content.split("\n").length} of ${fileInfo.lineCount} lines — too large to include in full`
    : `${fileInfo.lineCount} line${fileInfo.lineCount === 1 ? "" : "s"}`;
}

// Every model shares the same 8192-token context (see get_llm() in
// server.py) — this is a conservative chars-per-token estimate (code runs
// more token-dense than prose, thanks to punctuation/symbols) used only to
// decide when a file needs truncating, not an exact count.
const MODEL_N_CTX = 8192;
const CHARS_PER_TOKEN_ESTIMATE = 3.2;
// Reserved for the system prompt, conversation-so-far, and the model's own
// reply — left over after that is what the file content is allowed to use.
const RESERVED_TOKENS = 2500;
const FILE_CHAR_BUDGET = (MODEL_N_CTX - RESERVED_TOKENS) * CHARS_PER_TOKEN_ESTIMATE;
// Above this, auto-switch off Fast & Light before attaching (see
// attachCodeFile) — a 1.5B model's answers on a file this size tend to be
// shallow regardless of whether it technically fits in context.
const LARGE_FILE_LINE_THRESHOLD = 150;

let pendingFile = null; // { filename, content, lineCount, truncated }

function showFileAttachError(text) {
  fileAttachStatus.textContent = text;
  fileAttachStatus.classList.remove("hidden");
  fileAttachStatus.classList.add("error");
}

function clearPendingFile() {
  pendingFile = null;
  fileAttachPreview.classList.add("hidden");
  fileAttachName.textContent = "";
  fileAttachStatus.classList.add("hidden");
}

async function attachCodeFile(file) {
  fileAttachStatus.classList.add("hidden");
  const text = await file.text().catch(() => null);
  if (text === null) { showFileAttachError(`Couldn't read "${file.name}".`); return; }

  const lines = text.split("\n");
  const isLarge = lines.length > LARGE_FILE_LINE_THRESHOLD || text.length > FILE_CHAR_BUDGET;

  // A big file gets a genuinely better read from a bigger model — Fast &
  // Light's answers on anything substantial tend to be shallow regardless
  // of whether the text technically fits in its context. Only steps up one
  // tier (never straight to Best Quality): that model is materially slower
  // to load and run, so jumping to it automatically would be a much bigger
  // surprise than Fast -> Balanced.
  let modelSwitchMsg = null;
  if (isLarge && activeModelCatalogId === "fast") {
    const balanced = findCatalogModel("balanced");
    if (balanced) {
      const result = await switchToModel(balanced.filename);
      if (result.ok) modelSwitchMsg = `"${balanced.label}"`;
    }
  }

  // Unconditional on size, unlike the model step-up above — the persona
  // shapes HOW the model answers, not how capable it is, so even a tiny
  // file benefits from Coding Helper's system prompt. Same reasoning as
  // the image-attach auto-switch: attaching a code file only ever means
  // one thing, so ask-first would just be friction.
  let personaSwitchMsg = null;
  if (currentPersona !== "coding_helper") {
    personaSelect.value = "coding_helper";
    currentPersona = "coding_helper";
    personaSwitchMsg = '"Coding Helper"';
  }

  if (modelSwitchMsg || personaSwitchMsg) {
    const parts = [modelSwitchMsg, personaSwitchMsg].filter(Boolean);
    showFileAttachInfo(`Switched to ${parts.join(" and ")} to review this file.`);
  }

  let content = text;
  let truncated = false;
  if (content.length > FILE_CHAR_BUDGET) {
    // Cut at a line boundary rather than mid-line so the truncated file at
    // least stays syntactically legible up to the cut point.
    let cut = content.lastIndexOf("\n", FILE_CHAR_BUDGET);
    if (cut === -1) cut = FILE_CHAR_BUDGET;
    content = content.slice(0, cut);
    truncated = true;
  }

  pendingFile = { filename: file.name, content, lineCount: lines.length, truncated };
  fileAttachName.textContent = truncated
    ? `${file.name} — first ${content.split("\n").length} of ${lines.length} lines (too large for full review)`
    : `${file.name} — ${lines.length} line${lines.length === 1 ? "" : "s"}`;
  fileAttachPreview.classList.remove("hidden");
}

function showFileAttachInfo(text) {
  fileAttachStatus.textContent = text;
  fileAttachStatus.classList.remove("hidden", "error");
}

fileAttachRemove.addEventListener("click", clearPendingFile);

// Drag-and-drop onto the compose bar — an image file (attach-for-this-
// message, see above), a recognized source file (attach-for-the-whole-
// conversation, see above), a PDF/Word/Excel/PowerPoint file (extracted
// and chunked server-side, see attachDocumentFile below), or plain text:
// either a dropped .txt/.md/log file, or a plain text *selection* dragged
// straight off a webpage/terminal/editor with no file involved at all
// ("copied text", the case that was actually built for — see
// ingestTextSnippet below). Told apart by what's actually in the drag: an
// image MIME type, a recognized code extension, a recognized document
// extension, a non-image file, or a bare "text/plain" payload with no
// Files entry at all.
form.addEventListener("dragover", (e) => {
  if (!e.dataTransfer || !e.dataTransfer.types) return;
  const types = e.dataTransfer.types;
  if (!types.includes("Files") && !types.includes("text/plain")) return;
  e.preventDefault();
  attachImageBtn.classList.add("drag-over");
});
form.addEventListener("dragleave", (e) => {
  if (e.target === form) attachImageBtn.classList.remove("drag-over");
});
form.addEventListener("drop", (e) => {
  if (!e.dataTransfer) return;
  attachImageBtn.classList.remove("drag-over");

  const files = e.dataTransfer.files;
  if (files && files.length > 0) {
    e.preventDefault();
    const file = files[0];
    if (file.type.startsWith("image/")) {
      attachImageFile(file);
    } else if (CODE_FILE_EXTENSIONS.has(fileExt(file.name))) {
      attachCodeFile(file);
    } else if (isDocumentFile(file)) {
      attachDocumentFile(file);
    } else {
      const reader = new FileReader();
      reader.onload = () => ingestTextSnippet(reader.result, file.name);
      reader.onerror = () => showTextSnippetStatus(`Couldn't read "${file.name}".`, true);
      reader.readAsText(file);
    }
    return;
  }

  const text = e.dataTransfer.getData("text/plain");
  if (text && text.trim()) {
    e.preventDefault();
    ingestTextSnippet(text, "dropped-text.txt");
  }
});

// ---------------------------------------------------------------------------
// Large-paste-to-attachment — pasting a big block of text (a stack trace,
// an error log) directly into the message box the normal way would either
// bloat every later message with it (kept in full in conversation history)
// or lose it the moment the reply comes back (nothing is ever re-sent
// automatically). Past a size threshold, treat it the same as a dropped
// text file instead: chunked, embedded, and searchable for the rest of
// this conversation, with the input box left clear for the actual
// question. A short paste is left completely alone — normal textarea
// behavior, nothing intercepted.
// ---------------------------------------------------------------------------
const PASTE_SNIPPET_THRESHOLD = 1200; // characters — roughly a substantial stack trace

input.addEventListener("paste", (e) => {
  const text = (e.clipboardData || window.clipboardData).getData("text/plain");
  if (!text || text.length < PASTE_SNIPPET_THRESHOLD) return; // short paste — let it land in the box normally
  e.preventDefault();
  ingestTextSnippet(text, "pasted-text.txt");
});

function showTextSnippetStatus(text, isError) {
  textSnippetStatus.textContent = text;
  textSnippetStatus.classList.remove("hidden");
  textSnippetStatus.classList.toggle("error", !!isError);
}

async function ingestTextSnippet(text, filename) {
  if (!text || !text.trim()) return;
  showTextSnippetStatus(`Reading ${filename}…`, false);
  try {
    const statusRes = await fetch("/api/documents");
    const statusData = await statusRes.json();
    if (!statusData.embedding_model_ready) {
      showTextSnippetStatus("Installing document reader (one-time, ~100MB)…", false);
      const installRes = await fetch("/api/documents/install-reader", { method: "POST" });
      const installData = await installRes.json();
      if (installData.error) { showTextSnippetStatus(installData.error, true); return; }
      const gotIt = await waitForEmbeddingModel();
      if (!gotIt) {
        showTextSnippetStatus("Document reader install is taking a while — try again in a moment.", true);
        return;
      }
    }

    const res = await fetch("/api/documents/paste-text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, filename, conversation_id: currentConvId || undefined }),
    });
    const data = await res.json();
    if (data.error) { showTextSnippetStatus(data.error, true); return; }

    // The very first thing pasted into a brand-new chat is what mints its
    // conversation id (see /api/documents/paste-text) — adopt it now so
    // this turn's /api/chat call and the eventual save both agree on it.
    if (data.conversation_id) currentConvId = data.conversation_id;

    textSnippetStatus.classList.add("hidden");
    if (data.duplicate) {
      addMessage("system", `📎 Already added: ${filename}`);
    } else {
      addMessage("system", `📎 Added ${filename} (${data.num_chunks} section${data.num_chunks === 1 ? "" : "s"}) — I can reference it in this conversation.`);
    }
  } catch {
    showTextSnippetStatus("Couldn't reach the app. Try again.", true);
  }
}

/** Same purpose and UI as ingestTextSnippet (a chunked, conversation-scoped
 * reference — never filed into the permanent Documents library), but for a
 * PDF/Word/Excel/PowerPoint file rather than plain text: the extraction
 * that turns it into text has to happen server-side (see
 * extract_document_text in rag.py), so this uploads the raw file instead
 * of reading it as text client-side first. Previously a document dropped
 * on the chat bar fell through to ingestTextSnippet's FileReader.readAsText
 * path, which mis-read its binary bytes as if they were already text. */
async function attachDocumentFile(file) {
  showTextSnippetStatus(`Reading ${file.name}…`, false);
  try {
    const statusRes = await fetch("/api/documents");
    const statusData = await statusRes.json();
    if (!statusData.embedding_model_ready) {
      showTextSnippetStatus("Installing document reader (one-time, ~100MB)…", false);
      const installRes = await fetch("/api/documents/install-reader", { method: "POST" });
      const installData = await installRes.json();
      if (installData.error) { showTextSnippetStatus(installData.error, true); return; }
      const gotIt = await waitForEmbeddingModel();
      if (!gotIt) {
        showTextSnippetStatus("Document reader install is taking a while — try again in a moment.", true);
        return;
      }
    }

    const formData = new FormData();
    formData.append("file", file);
    if (currentConvId) formData.append("conversation_id", currentConvId);
    const res = await fetch("/api/documents/upload-scoped", { method: "POST", body: formData });
    const data = await res.json();
    if (data.error) { showTextSnippetStatus(data.error, true); return; }

    if (data.conversation_id) currentConvId = data.conversation_id;

    textSnippetStatus.classList.add("hidden");
    if (data.duplicate) {
      addMessage("system", `📎 Already added: ${file.name}`);
    } else {
      addMessage("system", `📎 Added ${file.name} (${data.num_chunks} section${data.num_chunks === 1 ? "" : "s"}) — I can reference it in this conversation.`);
    }
  } catch {
    showTextSnippetStatus("Couldn't reach the app. Try again.", true);
  }
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  // While a reply is streaming, Send is standing in as Stop (see
  // setStreamingUi) — the click submits the form either way, so this is
  // where that repurposing actually takes effect.
  if (isStreaming) { stopGeneration(); return; }

  let text = input.value.trim();
  if (!text && !pendingImage && !pendingFile) return;
  if (!text && pendingImage) text = "Describe this image."; // a bare attachment still needs some prompt
  if (!text && pendingFile) text = "Please review this file.";

  const imageForThisTurn = pendingImage;
  const fileForThisTurn = pendingFile;
  addMessage("user", text, imageForThisTurn);
  if (fileForThisTurn) addFileAttachNote(chatWindow.lastElementChild, `${fileForThisTurn.filename} (${fileLineInfo(fileForThisTurn)})`);

  // An attached image or file already signals a different intent (analyze
  // this photo, review this file) — the image-generation auto-switch only
  // applies to a plain typed request, the same way Image Analysis's own
  // auto-switch only fires the other direction, off an actual attachment
  // rather than the wording of a message.
  if (!imageForThisTurn && !fileForThisTurn && IMAGE_GEN_REQUEST_RE.test(text)) {
    history.push({ role: "user", content: text });
    input.value = "";
    retireRoutingNotes();
    await generateImageFromPrompt(text);
    input.focus();
    return;
  }

  // An attached photo plus edit-intent wording (see IMAGE_EDIT_REQUEST_RE)
  // is the other hybrid path: Image Analysis reads the photo first, then
  // FLUX edits the actual pixels — not a text-only description of a
  // similar-sounding image the way IMAGE_GEN_REQUEST_RE's from-scratch
  // path works.
  if (imageForThisTurn && IMAGE_EDIT_REQUEST_RE.test(text)) {
    history.push({ role: "user", content: text });
    input.value = "";
    clearPendingImage();
    clearPendingFile();
    retireRoutingNotes();
    await editImageFromPrompt(text, imageForThisTurn);
    input.focus();
    return;
  }

  // The visible bubble shows just the question, but what actually goes to
  // the model — and what's kept in `history` for every later turn, unlike
  // the one-turn-only image — is the question plus the file's full text in
  // a fenced code block. See the CODE_FILE_EXTENSIONS comment above for why
  // this isn't chunked/embedded like a pasted snippet, and FILE_ATTACHMENT_RE
  // above for how this exact shape gets parsed back apart when reloading a
  // saved conversation.
  let content = text;
  if (fileForThisTurn) {
    const lang = LANG_BY_EXT[fileExt(fileForThisTurn.filename)] || "";
    content = `${text}\n\n[Attached file: ${fileForThisTurn.filename} (${fileLineInfo(fileForThisTurn)})]\n\`\`\`${lang}\n${fileForThisTurn.content}\n\`\`\``;
  }
  history.push({ role: "user", content });

  input.value = "";
  clearPendingImage();
  clearPendingFile();
  retireRoutingNotes();
  await sendToModel({ autoRoute: true, image: imageForThisTurn });
  input.focus();
});

/** Small label under a user bubble noting a file rode along with it — the
 * bubble itself only ever shows the typed question (see the submit
 * handler), never the file's full text, so this is the one visible trace
 * that it was attached. Same visual pattern as addStoppedNote/
 * addRoutingNote, just anchored to a user message instead of an assistant
 * one. Takes the already-built "filename (line info)" label rather than a
 * fileInfo object so openConversation() can reuse it too, reconstructing
 * the label from FILE_ATTACHMENT_RE's capture groups instead of a live
 * pendingFile. */
function addFileAttachNote(userEl, label) {
  const note = document.createElement("div");
  note.className = "routing-note note-right";
  note.textContent = `📄 ${label}`;
  userEl.insertAdjacentElement("afterend", note);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

/** Toggles the Send button between its normal role and a Stop control for
 * the duration of one streaming reply, rather than adding a second button —
 * the two actions are never both valid at once, so one control can do both. */
function setStreamingUi(streaming) {
  isStreaming = streaming;
  sendBtn.textContent = streaming ? "Stop" : "Send";
  sendBtn.classList.toggle("stop-btn", streaming);
}

/** Aborts the in-flight fetch (for an instant UI response) and tells the
 * backend to cut generation short too — an aborted fetch alone leaves the
 * model still generating server-side until it hits its token limit. */
function stopGeneration() {
  if (currentAbortController) currentAbortController.abort();
  fetch("/api/chat/stop", { method: "POST" }).catch(() => {});
}

/** Strips the retry button from any earlier routing note.
 *
 * The retry works by popping the last assistant turn off history — which is
 * only the right turn while that answer IS the last one. Once a newer message
 * has been sent, an old note's button would discard the wrong answer and
 * delete the wrong bubble, leaving the transcript and the model's history
 * describing two different conversations. The note's label stays as a record
 * of what happened; only the now-unsafe action goes away. */
function retireRoutingNotes() {
  for (const note of chatWindow.querySelectorAll(".routing-note")) {
    const btn = note.querySelector("button");
    if (btn) btn.remove();
  }
}

/** Sends the current history to the model and streams the reply.
 *
 * autoRoute=false is what the "search everything instead" link uses: the
 * question is re-asked unchanged with category steering turned off. That
 * escape hatch is the reason automatic routing is defensible — the router
 * gets to be wrong, as long as being wrong is visible and cheap to undo. */
async function sendToModel({ autoRoute, image }) {
  setStreamingUi(true);
  compactSuggestion.classList.add("hidden"); // re-evaluated by maybeSuggestCompact() once this turn finishes
  currentAbortController = new AbortController();
  const assistantEl = addMessage("assistant", "");
  showThinking(assistantEl);
  let full = "";
  let routedCategory = null;
  let routedPriority = null;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: history,
        persona: currentPersona,
        use_documents: true,
        auto_route: autoRoute,
        image: image || undefined,
        conversation_id: currentConvId || undefined,
      }),
      signal: currentAbortController.signal,
    });

    if (!res.ok) {
      const err = await res.json();
      hideThinking(assistantEl);
      const message = err.error || "Something went wrong. Please try again.";
      assistantEl.textContent = message;
      addErrorNote(assistantEl, message, { httpStatus: res.status });
      setStreamingUi(false);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streamError = null;

    outer:
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = JSON.parse(line.slice(6));
        if (payload.meta && payload.meta.category) {
          routedCategory = payload.meta.category;
        }
        if (payload.meta && payload.meta.priority) {
          routedPriority = payload.meta.priority;
        }
        if (payload.token) {
          if (!full) hideThinking(assistantEl); // first token — replace the indicator with real text
          full += payload.token;
          applyMarkdown(assistantEl, full);
          chatWindow.scrollTop = chatWindow.scrollHeight;
        }
        if (payload.error) {
          // Generation failed partway through on the backend (see
          // token_stream()'s try/except in server.py) rather than the
          // connection itself breaking — a real, specific failure, not the
          // generic "couldn't reach the engine" the outer catch below is
          // for. Stop reading; handled the same way below as everything
          // else that can end a reply early.
          streamError = payload.error;
          break outer;
        }
      }
    }
    hideThinking(assistantEl); // covers a reply that ended with zero tokens (e.g. an immediately empty stream)

    if (streamError) {
      // Same "keep whatever was generated, note how it ended" treatment as
      // an aborted reply — an error after some real output still leaves
      // that output worth keeping.
      if (full.trim()) {
        applyMarkdown(assistantEl, full);
        history.push({ role: "assistant", content: full });
        addErrorNote(assistantEl, streamError, { partialReply: full });
        const speakBtn = addMessageActions(assistantEl, full, precedingUserMessage(history, history.length - 1));
        if (autoSpeakEnabled && speakBtn) startSpeaking(speakBtn, full);
        saveCurrentConversation();
      } else {
        assistantEl.textContent = streamError;
        addErrorNote(assistantEl, streamError, {});
      }
      currentAbortController = null;
      setStreamingUi(false);
      maybeSuggestCompact();
      return;
    }

    history.push({ role: "assistant", content: full });
    if (routedCategory && routedCategory.auto) {
      addRoutingNote(assistantEl, { text: `Searched your ${routedCategory.name} documents first` });
    } else if (routedPriority) {
      addRoutingNote(assistantEl, { text: `Prioritized ${routedPriority.names.join(", ")} for this agent` });
    }
    if (full.trim()) {
      const speakBtn = addMessageActions(assistantEl, full, precedingUserMessage(history, history.length - 1));
      if (autoSpeakEnabled && speakBtn) startSpeaking(speakBtn, full);
    }
    saveCurrentConversation();
    // Cheap no-op if this message wasn't a "remember that ..." request —
    // only refreshes the sidebar list when the backend actually added one.
    loadMemory();
  } catch (err) {
    hideThinking(assistantEl);
    if (err.name === "AbortError") {
      // User-initiated stop, not a failure — keep whatever was generated so
      // far rather than discarding it. An empty bubble (stopped before the
      // first token arrived) has nothing worth keeping, so it's removed
      // instead of leaving a blank message in the transcript.
      if (full.trim()) {
        applyMarkdown(assistantEl, full);
        history.push({ role: "assistant", content: full });
        addStoppedNote(assistantEl);
        const speakBtn = addMessageActions(assistantEl, full, precedingUserMessage(history, history.length - 1));
        if (autoSpeakEnabled && speakBtn) startSpeaking(speakBtn, full);
        saveCurrentConversation();
      } else {
        assistantEl.remove();
      }
    } else {
      const message = "Couldn't reach the local AI engine. Try restarting the app.";
      assistantEl.textContent = message;
      addErrorNote(assistantEl, message, { exception: String(err) });
    }
  }

  currentAbortController = null;
  setStreamingUi(false);
  maybeSuggestCompact();
}

function addRoutingNote(assistantEl, { text }) {
  const note = document.createElement("div");
  note.className = "routing-note";
  const label = document.createElement("span");
  label.textContent = text;
  const redo = document.createElement("button");
  redo.className = "link-btn";
  redo.textContent = "search everything instead";
  redo.addEventListener("click", () => {
    // Drop the routed answer from both the transcript and the model's
    // history, so the retry is a clean re-ask rather than a follow-up
    // question about an answer we're discarding.
    if (history.length && history[history.length - 1].role === "assistant") history.pop();
    note.remove();
    assistantEl.remove();
    sendToModel({ autoRoute: false });
  });
  note.appendChild(label);
  note.appendChild(redo);
  assistantEl.insertAdjacentElement("afterend", note);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

/** Same small label under the bubble as addRoutingNote, but with no retry
 * button — "stopped early" isn't a decision the model made that a link
 * could redo, just a fact about how the reply ended. */
function addStoppedNote(assistantEl) {
  const note = document.createElement("div");
  note.className = "routing-note";
  note.textContent = "Stopped";
  assistantEl.insertAdjacentElement("afterend", note);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

/** The reverse of attaching a photo for Image Analysis: auto-switches on a
 * plain text request (see IMAGE_GEN_REQUEST_RE) into generating a new
 * image instead of replying with text. A whole image has to finish before
 * there's anything to show, so this is a single request/response, not a
 * token stream like sendToModel.
 *
 * The generated image is shown in the transcript but deliberately NOT
 * embedded as base64 in `history` sent back to the model on later turns —
 * same reasoning the README already gives for an attached photo: it rides
 * along for this one exchange, not every later message's context. A short
 * text marker stands in for it in history instead, so a follow-up
 * question still has *something* to refer back to. */
async function generateImageFromPrompt(prompt) {
  setStreamingUi(true);
  const assistantEl = addMessage("assistant", "");
  showThinking(assistantEl);

  try {
    const res = await fetch("/api/generate-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    const data = await res.json();
    hideThinking(assistantEl);

    if (!res.ok || data.error) {
      const message = data.error || "Couldn't generate that image. Try again.";
      assistantEl.textContent = message;
      addErrorNote(assistantEl, message, { httpStatus: res.status });
      history.push({ role: "assistant", content: `[Image generation failed: ${message}]` });
    } else {
      const img = document.createElement("img");
      img.src = `data:image/png;base64,${data.image_base64}`;
      img.className = "msg-image";
      img.alt = prompt;
      assistantEl.appendChild(img);
      history.push({ role: "assistant", content: `[Generated an image: ${prompt}]` });
      saveCurrentConversation();
    }
  } catch {
    hideThinking(assistantEl);
    const message = "Couldn't reach the app. Try again.";
    assistantEl.textContent = message;
    addErrorNote(assistantEl, message, {});
  }

  setStreamingUi(false);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

/** The hybrid path IMAGE_EDIT_REQUEST_RE triggers: an attached photo plus
 * a requested change edits the actual image rather than just describing
 * it. Two model calls, not one — Image Analysis (MiniCPM-V 2.6, already the
 * model an attached image auto-switches to) reads the photo and turns the
 * request into a concrete visual description first, since FLUX itself has
 * no way to read an image's content, only generate/edit pixels from a text
 * prompt. That description, plus the original photo as FLUX's starting
 * point (see generate_image's init_image/strength in imagegen.py), is what
 * actually produces the edit — not a fresh image generated from the
 * description alone, which would drop everything about the original photo
 * FLUX was never told to preserve.
 *
 * The intermediate description is never shown as its own reply — from the
 * user's side this is one turn (photo + request in, edited photo out),
 * even though it costs two model calls under the hood. */
async function editImageFromPrompt(request, imageDataUrl) {
  setStreamingUi(true);
  const assistantEl = addMessage("assistant", "");
  showThinking(assistantEl);
  const base64 = imageDataUrl.slice(imageDataUrl.indexOf(",") + 1);

  try {
    const describeRes = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{
          role: "user",
          content: `This photo needs this edit applied: "${request}". Write a short image-generator prompt (under 50 words) describing the photo WITH that change already made. Start the very first sentence with the change itself, stated plainly (what's now different and its new color/appearance) — don't bury it after other scene details, since the image generator's text encoder weights early words most heavily and may truncate long descriptions. After that, briefly add only the supporting details needed to keep the rest of the photo recognizable (composition, setting, lighting). End with one short sentence restating the change. No commentary, no preamble, no mention of "edit" or "change" as a concept — just describe the resulting image directly.`,
        }],
        persona: "default",
        use_documents: false,
        image: imageDataUrl,
      }),
    });
    if (!describeRes.ok) {
      const err = await describeRes.json();
      throw new Error(err.error || "Couldn't read that image.");
    }
    const reader = describeRes.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let description = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = JSON.parse(line.slice(6));
        if (payload.token) description += payload.token;
        if (payload.error) throw new Error(payload.error);
      }
    }
    description = description.trim();
    if (!description) throw new Error("Couldn't describe that image.");

    const editRes = await fetch("/api/generate-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: description, init_image_base64: base64 }),
    });
    const editData = await editRes.json();
    hideThinking(assistantEl);

    if (!editRes.ok || editData.error) {
      const message = editData.error || "Couldn't edit that image. Try again.";
      assistantEl.textContent = message;
      addErrorNote(assistantEl, message, { httpStatus: editRes.status });
      history.push({ role: "assistant", content: `[Image edit failed: ${message}]` });
    } else {
      const img = document.createElement("img");
      img.src = `data:image/png;base64,${editData.image_base64}`;
      img.className = "msg-image";
      img.alt = request;
      assistantEl.appendChild(img);
      history.push({ role: "assistant", content: `[Edited the attached image: ${request}]` });
      saveCurrentConversation();
    }
  } catch (err) {
    hideThinking(assistantEl);
    const message = err.message || "Couldn't reach the app. Try again.";
    assistantEl.textContent = message;
    addErrorNote(assistantEl, message, {});
  }

  setStreamingUi(false);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

/** Same pattern again, but for a reply that ended because generation
 * genuinely failed partway through (see token_stream()'s error payload) —
 * styled as an error rather than a neutral status, since unlike a stop this
 * wasn't something the user asked for. */
/** Assembles a plain-text bundle for the "Copy diagnostic info" button —
 * enough for a non-technical field tester to paste into a bug report
 * without having to describe what happened themselves. Deliberately scoped
 * to just the one failed exchange (the error itself, the message that
 * triggered it, and any partial reply) rather than the whole conversation —
 * plenty to debug from, without bloating the clipboard or copying
 * unrelated content the user might not expect to share. */
function buildDiagnosticText(message, { httpStatus, partialReply, exception } = {}) {
  const lastUser = [...history].reverse().find((m) => m.role === "user");
  const modelLabel = modelSelect.options[modelSelect.selectedIndex]?.textContent || modelSelect.value || "(none)";
  const lines = [
    "PocketMind diagnostic info",
    `Version: ${appVersion.textContent || "(unknown)"}`,
    `Time: ${new Date().toISOString()}`,
    `Model: ${modelLabel}`,
    `Persona: ${currentPersona}`,
    `Hardware: ${hardwareLabel.textContent || "(unknown)"}`,
    `Conversation: ${currentConvId || "(not yet saved)"}`,
    `Error: ${message}`,
  ];
  if (httpStatus) lines.push(`HTTP status: ${httpStatus}`);
  if (exception) lines.push(`Exception: ${exception}`);
  if (lastUser) lines.push(`Last message sent: ${lastUser.content.slice(0, 500)}`);
  if (partialReply) lines.push(`Partial reply before failure: ${partialReply.slice(0, 500)}`);
  return lines.join("\n");
}

function addErrorNote(assistantEl, message, diagnosticContext) {
  const note = document.createElement("div");
  note.className = "routing-note note-danger";
  const label = document.createElement("span");
  label.textContent = message;
  note.appendChild(label);

  if (diagnosticContext) {
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "link-btn";
    copyBtn.textContent = "Copy diagnostic info";
    copyBtn.addEventListener("click", async () => {
      const text = buildDiagnosticText(message, diagnosticContext);
      const revert = () => { copyBtn.textContent = "Copy diagnostic info"; };
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.textContent = "Copied";
      } catch {
        copyBtn.textContent = "Couldn't copy";
      }
      setTimeout(revert, 2000);
    });
    note.appendChild(copyBtn);
  }

  assistantEl.insertAdjacentElement("afterend", note);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

// ---------------------------------------------------------------------------
// Read-aloud — uses the browser's own built-in text-to-speech
// (SpeechSynthesis), not a downloaded model. Restricted to local/on-device
// voices only (voice.localService === true): some browsers also offer
// cloud-backed voices, and using one of those would quietly break this
// app's "nothing leaves this computer" promise the same way an internet
// model download would.
// ---------------------------------------------------------------------------
let speakingBtn = null; // the currently-active speak button, if any

function stopSpeaking() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  if (speakingBtn) {
    speakingBtn.classList.remove("speaking");
    speakingBtn.title = "Read aloud";
    speakingBtn = null;
  }
}

/** Removes markdown syntax that would otherwise be read aloud literally
 * (e.g. "asterisk asterisk bold asterisk asterisk") — not a full markdown
 * parser, just the characters/patterns renderMarkdown() actually produces. */
function stripMarkdownForSpeech(text) {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^>\s?/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/^-{3,}$/gm, "")
    .trim();
}

function getPreferredVoice() {
  const voices = window.speechSynthesis.getVoices().filter((v) => v.localService);
  if (voices.length === 0) return null;
  const lang = document.documentElement.lang || "en";
  return voices.find((v) => v.lang.startsWith(lang)) || voices[0];
}

/** Starts reading `text` aloud, reflecting the active state on `btn` (the
 * per-message speak button — shared by a manual click and auto-speak). */
function startSpeaking(btn, text) {
  stopSpeaking();
  const clean = stripMarkdownForSpeech(text);
  if (!clean) return;
  const utterance = new SpeechSynthesisUtterance(clean);
  const voice = getPreferredVoice();
  if (voice) utterance.voice = voice;
  utterance.onend = () => stopSpeaking();
  utterance.onerror = () => stopSpeaking();
  speakingBtn = btn;
  btn.classList.add("speaking");
  btn.title = "Stop reading";
  window.speechSynthesis.speak(utterance);
}

function createSpeakButton(text) {
  if (!("speechSynthesis" in window)) return null; // no TTS support — nothing to add
  const btn = document.createElement("button");
  btn.className = "speak-btn";
  btn.title = "Read aloud";
  btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="4 8 4 16 9 16 14 20 14 4 9 8 4 8"></polygon><path d="M17.5 8.5a5 5 0 0 1 0 7"></path></svg>';
  btn.addEventListener("click", () => {
    if (speakingBtn === btn) {
      stopSpeaking();
      return;
    }
    startSpeaking(btn, text);
  });
  return btn;
}

/** POSTs `text` to a docgen export endpoint and saves whatever comes back
 * as a file — shared by the Word and Excel download buttons below, since
 * the two only differ in endpoint/icon/filename, not in how the download
 * itself works. Returns whether it succeeded, so callers can decide how
 * to handle failure without this needing to know about button state. */
async function downloadExport(endpoint, text, filename) {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, title: history.find((m) => m.role === "user")?.content.slice(0, 60) }),
  });
  if (!res.ok) return false;
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
  return true;
}

function createWordDownloadButton(text) {
  const btn = document.createElement("button");
  btn.className = "speak-btn";
  btn.title = "Download as Word document";
  btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"></path><path d="M7 10l5 5 5-5"></path><path d="M4 19h16"></path></svg>';
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try { await downloadExport("/api/documents/export-docx", text, "response.docx"); }
    catch { /* best-effort — no dedicated error UI, matching the code-block download button's own silence on failure */ }
    btn.disabled = false;
  });
  return btn;
}

// Matches docgen.py's TABLE_ROW_RE/TABLE_SEP_RE on the export side — a
// pipe-table row followed by a "---|---" separator row confirms an actual
// markdown table, not just a line that happens to contain "|". Used to
// decide whether the Excel download button is worth showing at all: a
// plain paragraph of prose doesn't mean anything as a spreadsheet.
function hasMarkdownTable(text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  for (let i = 0; i < lines.length - 1; i++) {
    if (/^\|(.+)\|\s*$/.test(lines[i]) && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1].trim())) return true;
  }
  return false;
}

function createExcelDownloadButton(text) {
  const btn = document.createElement("button");
  btn.className = "speak-btn";
  btn.title = "Download table as Excel spreadsheet";
  btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M3 9h18"></path><path d="M3 15h18"></path><path d="M9 3v18"></path></svg>';
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try { await downloadExport("/api/documents/export-xlsx", text, "response.xlsx"); }
    catch { /* best-effort, same as the Word button */ }
    btn.disabled = false;
  });
  return btn;
}

function createPptxDownloadButton(text) {
  const btn = document.createElement("button");
  btn.className = "speak-btn";
  btn.title = "Download as PowerPoint slides";
  btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="14" rx="2"></rect><path d="M8 21h8"></path><path d="M12 17v4"></path></svg>';
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try { await downloadExport("/api/documents/export-pptx", text, "response.pptx"); }
    catch { /* best-effort, same as the Word button */ }
    btn.disabled = false;
  });
  return btn;
}

function createCopyTextButton(text) {
  const btn = document.createElement("button");
  btn.className = "speak-btn";
  btn.title = "Copy text";
  btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      btn.title = "Copied";
      btn.classList.add("speaking"); // reuses the speak button's own "active" tint, not a separate style
    } catch {
      btn.title = "Couldn't copy";
    }
    setTimeout(() => {
      btn.title = "Copy text";
      btn.classList.remove("speaking");
    }, 2000);
  });
  return btn;
}

// Word and PowerPoint used to show under every single reply, even a
// one-line answer — clutter most replies never needed. These decide
// whether a reply actually looks like something worth turning into that
// file type, so the buttons only show up when they'd produce something
// worth downloading.
function looksWordWorthy(text) {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  const hasHeading = /^#{1,6}\s+/m.test(text);
  const hasList = /^[-*]\s+\S|^\d+\.\s+\S/m.test(text);
  const hasMultipleParagraphs = text.trim().split(/\n\s*\n/).filter((p) => p.trim()).length >= 3;
  return words >= 120 || hasHeading || hasList || hasMultipleParagraphs;
}

// Mirrors docgen.py's own one-slide-per-heading approach (see
// markdown_to_pptx) — the button only appears when a real, multi-part deck
// would actually result, not a single slide with everything crammed in.
function looksSlideWorthy(text) {
  return /^#{1,6}\s+/m.test(text);
}

// Whatever the content looks like, an explicit ask always wins — matched
// against the user's own message, not the reply, since that's where "put
// this in a word doc" or "make it a spreadsheet" would actually be said.
const WORD_REQUEST_RE = /\bword\s+doc(?:ument)?\b|\.docx\b/i;
const EXCEL_REQUEST_RE = /\bexcel\b|\bspreadsheet\b|\.xlsx\b/i;
const PPTX_REQUEST_RE = /\bpower\s*point\b|\bslide(?:s|show)?\b|\bdeck\b|\bpresentation\b|\.pptx\b/i;

// An action verb near an image-ish noun, not either alone — "draw" or
// "generate" by itself catches far too much ("draw a conclusion",
// "generate a report") to trigger on its own the way the export-format
// regexes above safely can.
const IMAGE_GEN_REQUEST_RE = /\b(?:generate|create|draw|make|produce|render)\b(?:\s+\w+){0,3}\s+\b(?:image|picture|photo|illustration|drawing|artwork|painting|logo|icon|graphic)\b/i;

// Only ever checked when an image is actually attached (see the form
// handler), which is most of why this can stay broader than
// IMAGE_GEN_REQUEST_RE above — "this"/"it" unambiguously means the
// attached photo in that context, so bare edit verbs are enough on their
// own without needing a nearby image-ish noun the way a from-scratch
// generation request does. "make"/"turn" specifically still require
// "this"/"it" right after, since those two are common in ordinary
// non-edit questions about a photo ("what does this make you think of").
const IMAGE_EDIT_REQUEST_RE = /\b(?:change|alter|edit|modify|transform|add|remove|replace|recolor|repaint|redraw|convert)\b|\b(?:make|turn)\s+(?:this|it)\b/i;

/** Finds the user message that prompted history[index] — walks backward
 * rather than just taking history's last user turn, since replaying a
 * whole saved conversation (openConversation) calls this once per
 * assistant message, each with a different one. */
function precedingUserMessage(msgs, index) {
  for (let i = index - 1; i >= 0; i--) {
    if (msgs[i].role === "user") return msgs[i].content;
  }
  return "";
}

/** Appends the shared actions row under an assistant message: a copy-text
 * button (always present), read-aloud, and download-as-Word/Excel/
 * PowerPoint — each of the three export buttons only when the reply
 * actually looks like something worth exporting that way, or the user's
 * own message directly asked for that format. Kept as one function rather
 * than separate appendChild calls at each of this file's 4 call sites so
 * the row is always built the same way, and to keep returning the speak
 * button alone for the auto-speak-on-completion check those call sites
 * already do. */
function addMessageActions(assistantEl, text, userQuestion = "") {
  const row = document.createElement("div");
  row.className = "msg-actions";

  row.appendChild(createCopyTextButton(text));

  if (WORD_REQUEST_RE.test(userQuestion) || looksWordWorthy(text)) {
    row.appendChild(createWordDownloadButton(text));
  }
  if (EXCEL_REQUEST_RE.test(userQuestion) || hasMarkdownTable(text)) {
    row.appendChild(createExcelDownloadButton(text));
  }
  if (PPTX_REQUEST_RE.test(userQuestion) || looksSlideWorthy(text)) {
    row.appendChild(createPptxDownloadButton(text));
  }

  const speakBtn = createSpeakButton(text);
  if (speakBtn) row.appendChild(speakBtn);
  assistantEl.appendChild(row);
  return speakBtn;
}

// ---------------------------------------------------------------------------
// Auto-speak toggle — between the image and mic buttons. When on, every new
// AI reply starts reading itself aloud automatically the moment it finishes
// streaming (see the addMessageActions call in sendToModel), reusing the exact
// same per-message speak button/state so the two controls never disagree
// about what's currently playing. Session-only, like the sidebar-collapsed
// preference elsewhere in this app — not persisted to browser storage.
// ---------------------------------------------------------------------------
let autoSpeakEnabled = false;

autoSpeakBtn.addEventListener("click", () => {
  autoSpeakEnabled = !autoSpeakEnabled;
  autoSpeakBtn.classList.toggle("active", autoSpeakEnabled);
  autoSpeakBtn.setAttribute("aria-pressed", String(autoSpeakEnabled));
  autoSpeakBtn.title = autoSpeakEnabled
    ? "Auto-read AI responses: on (click to turn off)"
    : "Read AI responses aloud automatically";
  if (!autoSpeakEnabled) stopSpeaking();
});

// ---------------------------------------------------------------------------
// Voice input — records mono 16kHz PCM in the browser and encodes a WAV
// file directly (no external codec/ffmpeg needed on either end).
// ---------------------------------------------------------------------------
let audioCtx = null;
let mediaStream = null;
let processor = null;
let recordedSamples = [];
let isRecording = false;

async function startRecording() {
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioCtx.createMediaStreamSource(mediaStream);
  processor = audioCtx.createScriptProcessor(4096, 1, 1);
  recordedSamples = [];

  processor.onaudioprocess = (e) => {
    const channelData = e.inputBuffer.getChannelData(0);
    recordedSamples.push(new Float32Array(channelData));
  };

  source.connect(processor);
  processor.connect(audioCtx.destination);
  isRecording = true;
  micBtn.classList.add("recording");
}

function stopRecording() {
  isRecording = false;
  micBtn.classList.remove("recording");
  processor?.disconnect();
  mediaStream?.getTracks().forEach((t) => t.stop());

  const sampleRate = audioCtx.sampleRate;
  const totalLength = recordedSamples.reduce((sum, arr) => sum + arr.length, 0);
  const merged = new Float32Array(totalLength);
  let offset = 0;
  for (const arr of recordedSamples) { merged.set(arr, offset); offset += arr.length; }

  const wavBlob = encodeWav(merged, sampleRate, 16000);
  audioCtx.close();
  return wavBlob;
}

function encodeWav(float32Samples, inputRate, targetRate) {
  // Downsample to targetRate (simple linear resampling — fine for speech).
  const ratio = inputRate / targetRate;
  const outLength = Math.floor(float32Samples.length / ratio);
  const resampled = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    resampled[i] = float32Samples[Math.floor(i * ratio)];
  }

  const pcm16 = new Int16Array(resampled.length);
  for (let i = 0; i < resampled.length; i++) {
    const s = Math.max(-1, Math.min(1, resampled[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }

  const buffer = new ArrayBuffer(44 + pcm16.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)); };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + pcm16.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);        // PCM
  view.setUint16(22, 1, true);        // mono
  view.setUint32(24, targetRate, true);
  view.setUint32(28, targetRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, pcm16.length * 2, true);
  for (let i = 0; i < pcm16.length; i++) view.setInt16(44 + i * 2, pcm16[i], true);

  return new Blob([buffer], { type: "audio/wav" });
}

micBtn.addEventListener("click", async () => {
  if (!isRecording) {
    try {
      await startRecording();
    } catch {
      docStatus.textContent = "";
      alert("Couldn't access the microphone. Check your browser/OS permissions.");
    }
    return;
  }

  const wavBlob = stopRecording();
  input.placeholder = "Transcribing…";
  try {
    const res = await fetch("/api/transcribe", { method: "POST", body: wavBlob });
    const data = await res.json();
    if (data.text) {
      input.value = (input.value ? input.value + " " : "") + data.text;
    }
  } catch {
    alert("Couldn't transcribe. Try again.");
  }
  input.placeholder = "Ask something…";
  input.focus();
});

// ---------------------------------------------------------------------------
checkStatus();
setInterval(async () => {
  // Lightweight periodic poll — just keeps the "safe to unplug" indicator
  // accurate (e.g. once the model finishes loading into RAM on first
  // message) without re-triggering the heavier sidebar reloads.
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    updateEjectIndicator(data);
  } catch { /* transient */ }
}, 4000);
