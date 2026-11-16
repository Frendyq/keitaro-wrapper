var campaignId = $("#streams").data("campaign");
var streamsById = {};

function trendHtml(stats) {
  if (!stats) return "";
  var arrow = stats.trend > 0 ? "&#9650;" : stats.trend < 0 ? "&#9660;" : "&ndash;";
  var cls = stats.trend > 0 ? "up" : stats.trend < 0 ? "down" : "";
  return '<span class="trend ' + cls + '" title="Yesterday: ' + stats.yesterday_clicks + ' clicks">' + arrow + "</span>";
}

function statsHtml(stats) {
  if (!stats) return '<span class="hint">no clicks today</span>';
  return stats.clicks + " clicks, " + stats.conversions + " conv., " + stats.revenue + " revenue";
}

function offerRow(stream, offer) {
  var removed = offer.status === "removed";
  // Keitaro names usually start with the id already, do not repeat it.
  var hasId = String(offer.name).indexOf(String(offer.offer_id)) === 0;
  var label = escapeHtml(offer.name) + (hasId ? "" : ' <span class="hint">[' + offer.offer_id + "]</span>");
  var share = '<span class="share">' + offer.share + "%</span>";
  var pin = removed ? "" :
    '<button class="pin' + (offer.pinned ? " on" : "") + '" data-act="pin" title="Pin the weight">&#128204;</button>';
  var action = removed
    ? '<button class="btn small" data-act="restore">Bring back</button>'
    : '<button class="btn small danger" data-act="remove">Remove</button>';
  return '<tr class="' + (removed ? "row-removed" : "") + '" data-offer="' + offer.id + '">' +
    "<td>" + label + (removed ? ' <span class="badge">removed</span>' : "") + "</td>" +
    "<td>" + share + " " + pin + "</td>" +
    "<td>" + (removed ? "" : statsHtml(offer.stats)) + "</td>" +
    "<td>" + (removed ? "" : trendHtml(offer.stats)) + "</td>" +
    '<td style="text-align:right">' + action + "</td></tr>";
}

function streamHtml(stream) {
  var head = '<div class="stream-head"><div><span class="name">' + escapeHtml(stream.name) + "</span>" +
    (stream.dirty ? '<span class="badge warn">not published</span>' : "") + "</div></div>";
  if (!stream.has_offers) {
    return '<div class="stream" data-stream="' + stream.id + '">' + head +
      '<div class="stream-note">This stream has no offers, nothing to edit here.</div></div>';
  }
  var rows = stream.offers.map(function (o) { return offerRow(stream, o); }).join("");
  var table = '<table class="table"><thead><tr><th>Offer</th><th>Share</th><th>Stats (today)</th><th>Trend</th><th></th></tr></thead>' +
    "<tbody>" + (rows || '<tr><td colspan="5" class="hint">No offers</td></tr>') + "</tbody></table>";
  var add = '<div class="add-offer"><input class="offer-search" placeholder="Offer ID or name" autocomplete="off">' +
    '<button class="btn" data-act="add">Add</button><div class="suggest" hidden></div></div>';
  var bar = stream.dirty
    ? '<div class="actions-bar"><button class="btn primary" data-act="push">Push to KT</button>' +
      '<button class="btn" data-act="cancel">Cancel</button></div>'
    : "";
  return '<div class="stream' + (stream.dirty ? " dirty" : "") + '" data-stream="' + stream.id + '">' +
    head + table + add + bar + "</div>";
}

function renderStream(stream) {
  streamsById[stream.id] = stream;
  var html = streamHtml(stream);
  var existing = $('.stream[data-stream="' + stream.id + '"]');
  if (existing.length) {
    // The stats come with the whole campaign only, keep the ones we already have.
    existing.replaceWith(html);
  } else {
    $("#streams").append(html);
  }
}

function renderCampaign(campaign) {
  $("#streams").empty();
  campaign.streams.forEach(renderStream);
}

function reloadStream(streamId, fresh) {
  // After an edit we only get the stream back, carry over the stats from the previous render.
  var old = streamsById[streamId];
  fresh.offers.forEach(function (offer) {
    var before = old && old.offers.find(function (o) { return o.offer_id === offer.offer_id; });
    if (before) offer.stats = before.stats;
  });
  renderStream(fresh);
}

$("#streams").on("click", "[data-act]", function () {
  var button = $(this);
  var act = button.data("act");
  var streamId = button.closest(".stream").data("stream");
  var offerId = button.closest("tr").data("offer");
  var done = function (stream) { reloadStream(streamId, stream); };

  if (act === "remove") {
    api("DELETE", "/api/streams/" + streamId + "/offers/" + offerId).done(done);
  } else if (act === "restore") {
    api("POST", "/api/streams/" + streamId + "/offers/" + offerId + "/restore").done(done);
  } else if (act === "pin") {
    api("POST", "/api/streams/" + streamId + "/offers/" + offerId + "/pin", { pinned: !button.hasClass("on") }).done(done);
  } else if (act === "push") {
    api("POST", "/api/streams/" + streamId + "/push").done(function (stream) {
      showMessage("Published to Keitaro");
      loadCampaign();
    });
  } else if (act === "cancel") {
    api("POST", "/api/streams/" + streamId + "/cancel").done(done);
  } else if (act === "add") {
    var box = button.closest(".add-offer").find(".offer-search");
    var chosen = Number(box.data("chosen") || box.val());
    if (!chosen) { showMessage("Pick an offer first", "error"); return; }
    api("POST", "/api/streams/" + streamId + "/offers", { offer_id: chosen }).done(done);
  }
});

// Offer search with suggestions.
var searchTimer;
$("#streams").on("input", ".offer-search", function () {
  var box = $(this);
  box.removeData("chosen");
  var list = box.closest(".add-offer").find(".suggest");
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function () {
    api("GET", "/api/offers?q=" + encodeURIComponent(box.val())).done(function (offers) {
      list.html(offers.map(function (o) {
        var named = String(o.name).indexOf(String(o.id)) === 0;
        return '<div data-id="' + o.id + '">' + (named ? "" : "[" + o.id + "] ") + escapeHtml(o.name) + "</div>";
      }).join("") || '<div class="hint">Nothing found</div>').prop("hidden", false);
    });
  }, 250);
});

$("#streams").on("click", ".suggest div[data-id]", function () {
  var item = $(this);
  var box = item.closest(".add-offer").find(".offer-search");
  box.val(item.text()).data("chosen", item.data("id"));
  item.closest(".suggest").prop("hidden", true);
});

function loadCampaign() {
  api("GET", "/api/campaigns/" + campaignId).done(renderCampaign);
}

$("#fetch").on("click", function () {
  var button = $(this).prop("disabled", true);
  api("POST", "/api/campaigns/" + campaignId + "/fetch").done(function (campaign) {
    renderCampaign(campaign);
    showMessage("Streams fetched from Keitaro");
  }).always(function () { button.prop("disabled", false); });
});

loadCampaign();
