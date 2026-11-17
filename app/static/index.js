function loadCampaigns() {
  api("GET", "/api/campaigns").done(function (campaigns) {
    var rows = campaigns.map(function (c) {
      return "<tr><td>" + escapeHtml(c.name) + "</td><td>" + c.kt_id + "</td><td>" + escapeHtml(c.geo || "") +
        '</td><td><a class="btn small" href="/campaigns/' + c.id + '">Open editor</a></td></tr>';
    });
    $("#campaigns tbody").html(rows.join("") || '<tr><td colspan="4" class="hint">No campaigns yet</td></tr>');
  });
}

$("#create-form").on("submit", function (event) {
  event.preventDefault();
  var form = this;
  var button = $(form).find("button").prop("disabled", true);
  api("POST", "/api/campaigns", {
    name: form.name.value,
    geo: form.geo.value,
    offer_id: Number(form.offer_id.value),
  }).done(function (campaign) {
    showMessage("Campaign " + campaign.name + " created in Keitaro (id " + campaign.kt_id + ")");
    loadCampaigns();
  }).always(function () {
    button.prop("disabled", false);
  });
});

$("#import-form").on("submit", function (event) {
  event.preventDefault();
  var form = this;
  var button = $(form).find("button").prop("disabled", true);
  api("POST", "/api/campaigns/import", { kt_id: Number(form.kt_id.value) }).done(function (campaign) {
    window.location.href = "/campaigns/" + campaign.id;
  }).always(function () {
    button.prop("disabled", false);
  });
});

loadCampaigns();
