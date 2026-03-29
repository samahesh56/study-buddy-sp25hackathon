export function cleanCourseTitle(value) {
    if (!value) return "";
    return value.replace(/\s*\([^()]*\)\s*/g, " ").replace(/\s+/g, " ").trim();
}
