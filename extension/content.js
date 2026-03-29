let pendingScrollCount = 0;
let scrollFlushTimeout = null;
const APP_HOSTNAMES = new Set(["127.0.0.1", "localhost"]);
const isStudyClawAppPage = APP_HOSTNAMES.has(window.location.hostname);

function canUseExtensionRuntime() {
  return typeof chrome !== "undefined" && Boolean(chrome?.runtime?.id);
}

function isContextInvalidatedError(error) {
  const message = String(error?.message || error || "");
  return message.includes("Extension context invalidated");
}

function postExtensionBridgeError(requestId, error) {
  window.postMessage(
    {
      source: "studyclaw-extension",
      requestId,
      ok: false,
      error,
    },
    "*"
  );
}

function sendActivity(payload) {
  if (isStudyClawAppPage || !canUseExtensionRuntime()) {
    return;
  }

  try {
    chrome.runtime.sendMessage(
      {
        type: "content-activity",
        payload
      },
      () => chrome.runtime?.lastError
    );
  } catch (error) {
    if (!isContextInvalidatedError(error)) {
      throw error;
    }
  }
}

function flushScrollActivity() {
  if (pendingScrollCount === 0) {
    return;
  }

  sendActivity({
    scroll_count: pendingScrollCount,
    click_count: 0,
    keystroke_count: 0,
    page_visible: document.visibilityState === "visible",
    checkpoint_reason: "scroll_activity"
  });

  pendingScrollCount = 0;
  scrollFlushTimeout = null;
}

window.addEventListener(
  "scroll",
  () => {
    pendingScrollCount += 1;
    if (scrollFlushTimeout) {
      clearTimeout(scrollFlushTimeout);
    }
    scrollFlushTimeout = setTimeout(flushScrollActivity, 750);
  },
  { passive: true }
);

window.addEventListener("click", () => {
  sendActivity({
    scroll_count: 0,
    click_count: 1,
    keystroke_count: 0,
    page_visible: document.visibilityState === "visible",
    checkpoint_reason: "click_activity"
  });
});

window.addEventListener("keydown", () => {
  sendActivity({
    scroll_count: 0,
    click_count: 0,
    keystroke_count: 1,
    page_visible: document.visibilityState === "visible",
    checkpoint_reason: "keystroke_activity"
  });
});

document.addEventListener("visibilitychange", () => {
  flushScrollActivity();
  sendActivity({
    scroll_count: 0,
    click_count: 0,
    keystroke_count: 0,
    page_visible: document.visibilityState === "visible",
    checkpoint_reason: document.visibilityState === "visible" ? "page_visible" : "page_hidden"
  });
});

window.addEventListener("beforeunload", () => {
  flushScrollActivity();
  sendActivity({
    scroll_count: 0,
    click_count: 0,
    keystroke_count: 0,
    page_visible: document.visibilityState === "visible",
    checkpoint_reason: "page_unload"
  });
});

async function fetchCanvasCourses() {
  if (!window.location.hostname.endsWith("instructure.com")) {
    throw new Error("Canvas import must run from a Canvas tab.");
  }

  const domCourses = extractVisibleCanvasCourses();
  if (domCourses.length > 0) {
    return {
      canvas_instance_domain: window.location.hostname,
      courses: domCourses
    };
  }

  const response = await fetch("/api/v1/users/self/favorites/courses?per_page=100&include[]=term", {
    method: "GET",
    credentials: "include",
    headers: {
      Accept: "application/json"
    }
  });

  if (!response.ok) {
    throw new Error(`Canvas API request failed with ${response.status}`);
  }

  const courses = await response.json();
  const normalized = (Array.isArray(courses) ? courses : [])
    .map((course) => ({
      external_course_id: String(course.id),
      name: course.name,
      course_code: course.course_code || course.name,
      term_name: course.term?.name || null,
      workflow_state: course.workflow_state || null
    }))
    .filter((course) => course.external_course_id && course.name);

  const unique = [];
  const seen = new Set();
  for (const course of normalized) {
    const key = `${course.external_course_id}:${course.name}`;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(course);
    }
  }

  return {
    canvas_instance_domain: window.location.hostname,
    courses: unique
  };
}

function extractVisibleCanvasCourses() {
  const selectors = [
    "a.ic-DashboardCard__link[href*='/courses/']",
    ".ic-DashboardCard__header a[href*='/courses/']",
    "tr.course-list-table-row a[href*='/courses/']",
    ".course-list-table-row .course-list-course-title a[href*='/courses/']",
    ".course-list-favorite .name[href*='/courses/']"
  ];

  const links = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));
  const uniqueLinks = [];
  const seenLinks = new Set();
  for (const link of links) {
    const href = link.getAttribute("href") || "";
    if (!href.includes("/courses/")) {
      continue;
    }

    let normalizedHref = href;
    try {
      normalizedHref = new URL(href, window.location.origin).pathname;
    } catch {
      normalizedHref = href;
    }

    if (!/^\/courses\/\d+\/?$/.test(normalizedHref)) {
      continue;
    }

    if (!seenLinks.has(normalizedHref)) {
      seenLinks.add(normalizedHref);
      seenLinks.add(href);
      uniqueLinks.push(link);
    }
  }

  const courses = uniqueLinks
    .map((link) => {
      const href = link.getAttribute("href") || "";
      const match = href.match(/\/courses\/(\d+)/);
      const externalCourseId = match?.[1];
      const titleCandidate =
        link.getAttribute("aria-label") ||
        link.getAttribute("title") ||
        link.querySelector(".ic-DashboardCard__header-title")?.textContent ||
        link.querySelector(".name")?.textContent ||
        link.textContent;

      const name = normalizeVisibleCourseName(titleCandidate || "");
      if (!externalCourseId || !name) {
        return null;
      }

      return {
        external_course_id: externalCourseId,
        name,
        course_code: name,
        term_name: null,
        workflow_state: "visible"
      };
    })
    .filter(Boolean);

  const deduped = [];
  const seen = new Set();
  for (const course of courses) {
    const key = `${course.external_course_id}:${course.name}`;
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(course);
    }
  }

  return deduped;
}

function normalizeVisibleCourseName(value) {
  const name = value.replace(/\s+/g, " ").trim();
  return name
    .replace(/^(Announcements|Discussions|Assignments|Modules|Grades|Pages|Syllabus)\s*-\s*/i, "")
    .trim();
}

if (canUseExtensionRuntime()) {
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "background:canvas:get-courses") {
      fetchCanvasCourses()
        .then((result) => sendResponse({ ok: true, ...result }))
        .catch((error) => sendResponse({ ok: false, error: error.message }));
      return true;
    }

    return false;
  });
}

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  const data = event.data;
  if (!data || data.source !== "studyclaw-app" || !data.type || !data.requestId) return;

  const messageMap = {
    "app:start-session-control": "app:start-session-control",
    "app:stop-session-control": "app:stop-session-control",
    "app:import-canvas-courses": "app:import-canvas-courses",
    "app:get-extension-state": "app:get-extension-state"
  };

  const targetType = messageMap[data.type];
  if (!targetType) return;

  if (!canUseExtensionRuntime()) {
    postExtensionBridgeError(data.requestId, "StudyClaw extension is unavailable. Reload the extension and refresh the page.");
    return;
  }

  try {
    chrome.runtime.sendMessage(
      {
        type: targetType,
        payload: data.payload || {}
      },
      (response) => {
        const runtimeError = chrome.runtime?.lastError;
        if (runtimeError) {
          postExtensionBridgeError(data.requestId, runtimeError.message);
          return;
        }

        window.postMessage(
          {
            source: "studyclaw-extension",
            requestId: data.requestId,
            ok: Boolean(response?.ok),
            payload: response,
            error: response?.error || null
          },
          "*"
        );
      }
    );
  } catch (error) {
    if (isContextInvalidatedError(error)) {
      postExtensionBridgeError(
        data.requestId,
        "StudyClaw extension context was invalidated. Reload the extension and refresh the page."
      );
      return;
    }
    throw error;
  }
});
