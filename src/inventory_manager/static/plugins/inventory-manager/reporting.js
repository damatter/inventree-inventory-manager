const REPORTING_URL = "/plugin/inventory-manager/";

export function openReporting() {
    window.location.assign(REPORTING_URL);
}

export function renderReportingShortcut(target, context) {
    if (!target) {
        return;
    }

    const link = document.createElement("a");
    link.href = REPORTING_URL;
    link.textContent = "Reporting";
    link.title = "Open Reporting";
    link.setAttribute("aria-label", "Open Reporting");
    link.style.display = "flex";
    link.style.alignItems = "center";
    link.style.justifyContent = "center";
    link.style.boxSizing = "border-box";
    link.style.width = "100%";
    link.style.maxWidth = "100%";
    link.style.height = "100%";
    link.style.minHeight = "44px";
    link.style.padding = "0.45rem";
    link.style.borderRadius = "0.35rem";
    link.style.background = "#1971c2";
    link.style.color = "#fff";
    link.style.fontSize = "0.875rem";
    link.style.fontWeight = "600";
    link.style.lineHeight = "1.2";
    link.style.textAlign = "center";
    link.style.textDecoration = "none";
    link.style.whiteSpace = "nowrap";

    void context;
    target.innerHTML = "";
    target.style.height = "100%";
    target.appendChild(link);
}
