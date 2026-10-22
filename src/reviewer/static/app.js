const TERMINAL_STATUSES = new Set([
  "completed",
  "completed_partial",
  "failed",
]);
const POLL_INTERVAL_MS = 2000;

const form = document.getElementById("review-form");
const repositoryInput = document.getElementById("repository");
const commitShaInput = document.getElementById("commit-sha");
const submitButton = document.getElementById("submit-button");
const formError = document.getElementById("form-error");
const statusPanel = document.getElementById("status-panel");
const jobIdEl = document.getElementById("job-id");
const jobStatusEl = document.getElementById("job-status");
const loadingMessage = document.getElementById("loading-message");
const jobError = document.getElementById("job-error");
const reportPanel = document.getElementById("report-panel");
const findingsCount = document.getElementById("findings-count");
const emptyFindings = document.getElementById("empty-findings");
const findingsList = document.getElementById("findings-list");

function showError(element, message) {
  element.hidden = !message;
  element.textContent = message || "";
}

function parseApiError(payload, fallback) {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }
  const detail = payload.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item.msg || JSON.stringify(item))
      .join(" ");
  }
  return fallback;
}

async function readJsonResponse(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

function validateInputs(repository, commitSha) {
  if (!repository) {
    return "Enter a repository URL.";
  }
  const urlPattern = /^(https?:\/\/[^\s/$.?#].[^\s]*|git@[^\s:]+:[^\s]+)$/;
  if (!urlPattern.test(repository)) {
    return "Enter a valid HTTP, HTTPS, or SSH Git clone URL.";
  }
  if (!commitSha) {
    return "Enter a commit SHA.";
  }
  if (!/^[0-9a-fA-F]{40}$/.test(commitSha)) {
    return "Commit SHA must be a 40-character hexadecimal git hash.";
  }
  return "";
}

function setBusy(isBusy) {
  submitButton.disabled = isBusy;
  repositoryInput.disabled = isBusy;
  commitShaInput.disabled = isBusy;
}

function renderStatus(job) {
  statusPanel.hidden = false;
  jobIdEl.textContent = job.id;
  jobStatusEl.textContent = job.status;
  jobStatusEl.className = `status-badge ${job.status}`;
  const inProgress = !TERMINAL_STATUSES.has(job.status);
  loadingMessage.hidden = !inProgress;
  showError(jobError, job.error_message || "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function locationText(finding) {
  const path = finding.file_path || "Unknown file";
  if (finding.line == null) {
    return path;
  }
  return `${path}:${finding.line}`;
}

function renderFindings(findings) {
  reportPanel.hidden = false;
  findingsList.innerHTML = "";
  const total = findings.length;
  findingsCount.textContent = `${total} finding${total === 1 ? "" : "s"}`;
  emptyFindings.hidden = total !== 0;

  findings.forEach((finding) => {
    const severity = (finding.severity || "unknown").toLowerCase();
    const sourceBits = [finding.source, finding.rule_id]
      .filter(Boolean)
      .join(" · ");
    const article = document.createElement("article");
    article.className = `finding ${severity}`;
    article.innerHTML = `
      <div class="finding-top">
        <h3>${escapeHtml(finding.message || "Untitled issue")}</h3>
        <span class="severity">${escapeHtml(severity)}</span>
      </div>
      <p class="meta">${escapeHtml(locationText(finding))}</p>
      ${sourceBits ? `<p class="source">${escapeHtml(sourceBits)}</p>` : ""}
      <dl>
        <dt>Evidence</dt>
        <dd>${escapeHtml(finding.evidence || "No evidence provided.")}</dd>
        <dt>Recommendation</dt>
        <dd>${escapeHtml(
          finding.recommendation || "No recommendation provided.",
        )}</dd>
      </dl>
    `;
    findingsList.appendChild(article);
  });
}

async function fetchJob(jobId) {
  const response = await fetch(`/review/${jobId}`);
  const payload = await readJsonResponse(response);
  if (!response.ok) {
    throw new Error(parseApiError(payload, "Could not load job status."));
  }
  return payload;
}

async function fetchFindings(jobId) {
  const response = await fetch(`/review/${jobId}/findings`);
  const payload = await readJsonResponse(response);
  if (!response.ok) {
    throw new Error(parseApiError(payload, "Could not load findings."));
  }
  return payload;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollUntilDone(jobId) {
  let job = await fetchJob(jobId);
  renderStatus(job);
  while (!TERMINAL_STATUSES.has(job.status)) {
    await wait(POLL_INTERVAL_MS);
    job = await fetchJob(jobId);
    renderStatus(job);
  }
  return job;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError(formError, "");
  reportPanel.hidden = true;
  findingsList.innerHTML = "";

  const repository = repositoryInput.value.trim();
  const commitSha = commitShaInput.value.trim();
  const validationError = validateInputs(repository, commitSha);
  if (validationError) {
    showError(formError, validationError);
    return;
  }

  setBusy(true);
  loadingMessage.hidden = false;
  statusPanel.hidden = false;
  jobIdEl.textContent = "Submitting…";
  jobStatusEl.textContent = "queued";
  jobStatusEl.className = "status-badge queued";
  showError(jobError, "");

  try {
    const response = await fetch("/review/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repository,
        commit_sha: commitSha,
      }),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(parseApiError(payload, "Could not start the review."));
    }

    const job = await pollUntilDone(payload.id);
    if (job.status === "failed") {
      return;
    }
    const findings = await fetchFindings(job.id);
    renderFindings(findings);
  } catch (error) {
    showError(formError, error.message || "Something went wrong.");
  } finally {
    setBusy(false);
    loadingMessage.hidden = true;
  }
});
