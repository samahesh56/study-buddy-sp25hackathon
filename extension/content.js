let scrollCount = 0;
let clickCount = 0;
let keystrokeCount = 0;

function sendActivity() {
  if (scrollCount === 0 && clickCount === 0 && keystrokeCount === 0 && document.visibilityState === "visible") {
    return;
  }

  chrome.runtime.sendMessage(
    {
      type: "content-activity",
      payload: {
        scroll_count: scrollCount,
        click_count: clickCount,
        keystroke_count: keystrokeCount,
        page_visible: document.visibilityState === "visible"
      }
    },
    () => chrome.runtime.lastError
  );

  scrollCount = 0;
  clickCount = 0;
  keystrokeCount = 0;
}

window.addEventListener(
  "scroll",
  () => {
    scrollCount += 1;
  },
  { passive: true }
);

window.addEventListener("click", () => {
  clickCount += 1;
});

window.addEventListener("keydown", () => {
  keystrokeCount += 1;
});

document.addEventListener("visibilitychange", sendActivity);
window.addEventListener("beforeunload", sendActivity);
setInterval(sendActivity, 5000);

async function fetchCanvasCourses() {
  if (!window.location.hostname.endsWith("instructure.com")) {
    throw new Error("Canvas import must run from a Canvas tab.");
  }

  const response = await fetch("/api/v1/courses?per_page=100&enrollment_state=active&state[]=available&include[]=term", {
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

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "background:canvas:get-courses") {
    fetchCanvasCourses()
      .then((result) => sendResponse({ ok: true, ...result }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  return false;
});
