// Small helpers shared by the pages.
function showMessage(text, kind) {
  $("#message").attr("class", "message " + (kind || "ok")).text(text).prop("hidden", false);
  clearTimeout(showMessage._timer);
  showMessage._timer = setTimeout(function () { $("#message").prop("hidden", true); }, 6000);
}

function api(method, url, body) {
  return $.ajax({
    method: method,
    url: url,
    contentType: "application/json",
    data: body === undefined ? undefined : JSON.stringify(body),
  }).fail(function (xhr) {
    var detail = xhr.responseJSON && xhr.responseJSON.detail;
    if (Array.isArray(detail)) detail = detail.map(function (d) { return d.msg; }).join("; ");
    showMessage(detail || "Request failed (" + xhr.status + ")", "error");
  });
}

function escapeHtml(value) {
  return $("<div>").text(value == null ? "" : value).html();
}
