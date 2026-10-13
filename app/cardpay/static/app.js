// Small progressive enhancements. Every flow also works without JavaScript.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-open-dialog]").forEach((button) => {
    const dialog = document.getElementById(button.dataset.openDialog);
    button.addEventListener("click", () => dialog.showModal());
  });
  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog").close());
  });
  // A money form is sent once; the server also deduplicates by idempotency key.
  document.querySelectorAll("form[data-once]").forEach((form) => {
    form.addEventListener("submit", () => {
      form.querySelectorAll("button[type=submit]").forEach((b) => { b.disabled = true; });
    });
  });
});
