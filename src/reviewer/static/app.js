
const TERMINAL_STATUSES = new Set([
    "completed",
    "completed_partial",
    "failed",
]);

const POLLING_INTERVAL = 2000;

// Form elements
const reviewForm = document.getElementById("review-form");
const repositoryInput = document.getElementById("repository-url");
const commitInput = document.getElementById("commit-sha");
const submitButton = document.getElementById("submit-button");

// Status elements
const statusPanel = document.getElementById("status-panel");
const jobIdElement = document.getElementById("job-id");
const jobStatusElement = document.getElementById("job-status");
const loadingMessage = document.getElementById("loading-message");
const jobError = document.getElementById("job-error");

// Report elements
const reportPanel = document.getElementById("report-panel");
const reportRepository = document.getElementById("report-repository");
const reportCommit = document.getElementById("report-commit");
const reportStatus = document.getElementById("report-status");

const executiveSummary = document.getElementById("executive-summary");
const keyObservationsSection = document.getElementById(
    "key-observations-section"
);
const keyObservations = document.getElementById("key-observations");

const findingsCount = document.getElementById("findings-count");
const severityBreakdown = document.getElementById("severity-breakdown");
const categoryBreakdown = document.getElementById("category-breakdown");

const emptyFindings = document.getElementById("empty-findings");
const findingsList = document.getElementById("findings-list");

const actionsList = document.getElementById("actions-list");

const completionStatus = document.getElementById("completion-status");
const partialReview = document.getElementById("partial-review");

const agentFailuresSection = document.getElementById(
    "agent-failures-section"
);
const agentFailures = document.getElementById("agent-failures");

const limitationsSection = document.getElementById(
    "limitations-section"
);
const limitationsList = document.getElementById("limitations-list");

// Create a form error element because the updated HTML does not
// contain a separate form-error element.
const formError = document.createElement("p");
formError.className = "error-message";
formError.hidden = true;
reviewForm.appendChild(formError);


// --------------------------------------------------
// General Helpers
// --------------------------------------------------

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => {
        const entities = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;",
        };

        return entities[character];
    });
}


function displayValue(value, fallback = "Not available") {
    if (value === null || value === undefined || value === "") {
        return fallback;
    }

    if (typeof value === "object") {
        return JSON.stringify(value, null, 2);
    }

    return String(value);
}


function setText(element, value, fallback = "Not available") {
    element.textContent = displayValue(value, fallback);
}


function showFormError(message) {
    formError.textContent = message;
    formError.hidden = false;
}


function clearFormError() {
    formError.textContent = "";
    formError.hidden = true;
}


function showJobError(message) {
    jobError.textContent = message;
    jobError.hidden = false;
}


function hideJobError() {
    jobError.textContent = "";
    jobError.hidden = true;
}


function setBusy(isBusy) {
    submitButton.disabled = isBusy;
    submitButton.textContent = isBusy
        ? "Review in Progress..."
        : "Start Review";
}


function validateInputs() {
    const repository = repositoryInput.value.trim();
    const commitSha = commitInput.value.trim();

    if (!repository) {
        showFormError("Please enter a GitHub repository URL.");
        return false;
    }

    const githubPattern =
        /^https:\/\/github\.com\/[^/\s]+\/[^/\s]+(?:\.git)?\/?$/i;

    if (!githubPattern.test(repository)) {
        showFormError(
            "Please enter a valid HTTPS GitHub repository URL."
        );
        return false;
    }

    if (!/^[a-fA-F0-9]{40}$/.test(commitSha)) {
    showFormError(
        "Please enter a valid 40-character commit SHA."
    );
    return false;
}

    clearFormError();
    return true;
}


// --------------------------------------------------
// API Response Handling
// --------------------------------------------------

async function readJsonResponse(response) {
    const responseText = await response.text();

    let data;

    try {
        data = responseText ? JSON.parse(responseText) : {};
    } catch {
        throw new Error("The server returned an invalid response.");
    }

    if (!response.ok) {
        let message = "Something went wrong.";

        if (typeof data.detail === "string") {
            message = data.detail;
        } else if (data.detail) {
            message = JSON.stringify(data.detail);
        }

        throw new Error(message);
    }

    return data;
}


async function createReviewJob(repository, commitSha) {
    const payload = {
    repository,
};

    if (commitSha) {
        payload.commit_sha = commitSha;
}

    const response = await fetch("/review/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });

    return readJsonResponse(response);
}


async function fetchJob(jobId) {
    const response = await fetch(
        `/review/${encodeURIComponent(jobId)}`
    );

    return readJsonResponse(response);
}


async function fetchReport(jobId) {
    const response = await fetch(
        `/review/${encodeURIComponent(jobId)}/report`
    );

    return readJsonResponse(response);
}


// --------------------------------------------------
// Job Status
// --------------------------------------------------

function renderStatus(job) {
    const status = String(job.status || "unknown").toLowerCase();

    statusPanel.hidden = false;

    setText(jobIdElement, job.id);
    setText(jobStatusElement, status.toUpperCase());

    jobStatusElement.className = `status-badge ${escapeHtml(status)}`;

    const isRunning = !TERMINAL_STATUSES.has(status);

    loadingMessage.hidden = !isRunning;

    if (status === "failed") {
        showJobError(
            job.error_message || "The repository review failed."
        );
    } else {
        hideJobError();
    }
}


function wait(milliseconds) {
    return new Promise((resolve) => {
        setTimeout(resolve, milliseconds);
    });
}


async function pollUntilDone(jobId) {
    while (true) {
        const job = await fetchJob(jobId);

        renderStatus(job);

        const status = String(job.status || "").toLowerCase();

        if (TERMINAL_STATUSES.has(status)) {
            return job;
        }

        await wait(POLLING_INTERVAL);
    }
}

// --------------------------------------------------
// Reusable Report Rendering Helpers
// --------------------------------------------------

function renderList(element, items) {
    element.innerHTML = "";

    if (!Array.isArray(items) || items.length === 0) {
        return false;
    }

    element.innerHTML = items
        .map((item) => `<li>${escapeHtml(displayValue(item))}</li>`)
        .join("");

    return true;
}


function renderBreakdown(element, breakdown) {
    element.innerHTML = "";

    if (!breakdown || typeof breakdown !== "object") {
        return;
    }

    const entries = Object.entries(breakdown);

    if (entries.length === 0) {
        element.textContent = "No breakdown available.";
        return;
    }

    element.innerHTML = entries
        .map(([name, count]) => {
            return `
                <div class="breakdown-item">
                    <span>${escapeHtml(name.replaceAll("_", " "))}</span>
                    <strong>${escapeHtml(count)}</strong>
                </div>
            `;
        })
        .join("");
}


function normalizeClass(value) {
    const normalized = String(value || "unknown").toLowerCase();

    const allowedValues = [
        "critical",
        "high",
        "medium",
        "low",
        "info",
        "unknown",
    ];

    return allowedValues.includes(normalized)
        ? normalized
        : "unknown";
}


// --------------------------------------------------
// Detailed Findings
// --------------------------------------------------

function renderFindings(findings) {
    findingsList.innerHTML = "";

    if (!Array.isArray(findings) || findings.length === 0) {
        emptyFindings.hidden = false;
        return;
    }

    emptyFindings.hidden = true;

    findingsList.innerHTML = findings
        .map((finding) => {
            const severity = normalizeClass(finding.severity);

            const location = [
                finding.file_path,
                finding.line ? `Line ${finding.line}` : null,
                finding.column ? `Column ${finding.column}` : null,
            ]
                .filter(Boolean)
                .join(" · ");

            const metadata = [
                finding.category
                    ? `Category: ${finding.category}`
                    : null,
                finding.source
                    ? `Source: ${finding.source}`
                    : null,
                finding.rule_id
                    ? `Rule: ${finding.rule_id}`
                    : null,
                location || null,
                finding.confidence !== null &&
                finding.confidence !== undefined
                    ? `Confidence: ${finding.confidence}`
                    : null,
            ]
                .filter(Boolean)
                .map((item) => `<span>${escapeHtml(item)}</span>`)
                .join("");

            return `
                <article class="finding ${severity}">
                    <div class="finding-top">
                        <h3>${escapeHtml(
                            displayValue(finding.title, "Untitled finding")
                        )}</h3>

                        <span class="severity ${severity}">
                            ${escapeHtml(severity)}
                        </span>
                    </div>

                    <div class="finding-meta">
                        ${metadata}
                    </div>

                    ${
                        finding.explanation
                            ? `
                                <div class="finding-block">
                                    <h4>Explanation</h4>
                                    <p>${escapeHtml(finding.explanation)}</p>
                                </div>
                            `
                            : ""
                    }

                    ${
                        finding.evidence
                            ? `
                                <div class="finding-block">
                                    <h4>Evidence</h4>
                                    <pre>${escapeHtml(finding.evidence)}</pre>
                                </div>
                            `
                            : ""
                    }

                    ${
                        finding.recommendation
                            ? `
                                <div class="finding-block">
                                    <h4>Recommendation</h4>
                                    <p>${escapeHtml(finding.recommendation)}</p>
                                </div>
                            `
                            : ""
                    }
                </article>
            `;
        })
        .join("");
}


// --------------------------------------------------
// Recommended Actions
// --------------------------------------------------

function renderActions(actions) {
    actionsList.innerHTML = "";

    if (!Array.isArray(actions) || actions.length === 0) {
        actionsList.innerHTML = `
            <p class="empty-state">
                No recommended actions are available.
            </p>
        `;
        return;
    }

    actionsList.innerHTML = actions
        .map((action, index) => {
            const priority = action.priority ?? index + 1;

            const metadata = [
                action.severity
                    ? `Severity: ${action.severity}`
                    : null,
                action.category
                    ? `Category: ${action.category}`
                    : null,
                action.file_path || null,
                action.line ? `Line ${action.line}` : null,
            ]
                .filter(Boolean)
                .map((item) => `<span>${escapeHtml(item)}</span>`)
                .join("");

            return `
                <article class="action-item">
                    <div class="action-priority">
                        ${escapeHtml(priority)}
                    </div>

                    <div class="action-content">
                        <h3>
                            ${escapeHtml(
                                displayValue(action.title, "Recommended action")
                            )}
                        </h3>

                        <p>
                            ${escapeHtml(
                                displayValue(action.action)
                            )}
                        </p>

                        <div class="action-meta">
                            ${metadata}
                        </div>
                    </div>
                </article>
            `;
        })
        .join("");
}


// --------------------------------------------------
// Analysis Status and Limitations
// --------------------------------------------------

function renderAnalysisLimitations(analysis) {
    analysis = analysis || {};

    setText(
        completionStatus,
        analysis.completion_status
    );

    setText(
        partialReview,
        analysis.partial_review === true
            ? "Yes"
            : analysis.partial_review === false
                ? "No"
                : "Not available"
    );

    const hasFailures = renderList(
        agentFailures,
        analysis.agent_failures
    );

    agentFailuresSection.hidden = !hasFailures;

    const hasLimitations = renderList(
        limitationsList,
        analysis.limitations
    );

    limitationsSection.hidden = !hasLimitations;
}


// --------------------------------------------------
// Complete Report
// --------------------------------------------------

function renderReport(report) {
    if (!report || !report.overview) {
        throw new Error("The report response is missing its overview.");
    }

    const overview = report.overview;
    const summary = report.executive_summary || {};
    const findingsSummary = report.findings_summary || {};

    reportPanel.hidden = false;

    // Report header
    setText(reportRepository, overview.repository_url);
    setText(reportCommit, overview.commit_sha);
    setText(reportStatus, overview.status);

    // Executive summary
    setText(executiveSummary, summary.summary);

    const hasObservations = renderList(
        keyObservations,
        summary.key_observations
    );

    keyObservationsSection.hidden = !hasObservations;

    // Findings overview
    setText(
        findingsCount,
        findingsSummary.total ?? overview.total_findings ?? 0
    );

    renderBreakdown(
        severityBreakdown,
        findingsSummary.by_severity
    );

    renderBreakdown(
        categoryBreakdown,
        findingsSummary.by_category
    );

    // Detailed findings
    renderFindings(report.detailed_findings);

    // Recommended actions
    renderActions(report.recommended_actions);

    // Analysis status and limitations
    renderAnalysisLimitations(report.analysis_limitations);
}


// --------------------------------------------------
// Main Form Submission
// --------------------------------------------------

reviewForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    clearFormError();
    hideJobError();

    if (!validateInputs()) {
        return;
    }

    const repository = repositoryInput.value.trim();
    const commitSha = commitInput.value.trim();

    setBusy(true);

    statusPanel.hidden = true;
    reportPanel.hidden = true;

    try {
        // Step 1: Create review job
        const createdJob = await createReviewJob(
            repository,
            commitSha
        );

        if (!createdJob.id) {
            throw new Error(
                "The server did not return a review job ID."
            );
        }

        statusPanel.hidden = false;

        setText(jobIdElement, createdJob.id);
        setText(jobStatusElement, "QUEUED");

        loadingMessage.hidden = false;

        // Step 2: Poll until the job finishes
        const completedJob = await pollUntilDone(createdJob.id);

        const finalStatus = String(
            completedJob.status || ""
        ).toLowerCase();

        if (finalStatus === "failed") {
            return;
        }

        // Step 3: Fetch the complete saved report
        const report = await fetchReport(createdJob.id);

        // Step 4: Display the report
        renderReport(report);

        // Scroll to the report
        reportPanel.scrollIntoView({
            behavior: "smooth",
            block: "start",
        });

    } catch (error) {
        console.error("Review error:", error);

        if (statusPanel.hidden) {
            statusPanel.hidden = false;
        }

        loadingMessage.hidden = true;
        showJobError(error.message || "Unable to complete the review.");

    } finally {
        setBusy(false);
    }
});
