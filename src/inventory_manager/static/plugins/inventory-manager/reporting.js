const REPORTING_URL = "/plugin/inventory-manager/";

export function openReporting() {
    window.location.assign(REPORTING_URL);
}

export function renderReportingShortcut(target, context) {
    if (!target) {
        return;
    }

    const description = document.createElement("p");
    description.textContent = "Create replenishment reports and update stock settings.";

    const link = document.createElement("a");
    link.href = REPORTING_URL;
    link.textContent = "Open Reporting";
    link.style.display = "inline-block";
    link.style.padding = "0.55rem 0.9rem";
    link.style.borderRadius = "0.25rem";
    link.style.background = "#1971c2";
    link.style.color = "#fff";
    link.style.fontWeight = "600";
    link.style.textDecoration = "none";

    void context;
    target.innerHTML = "";
    target.appendChild(description);
    target.appendChild(link);
}
