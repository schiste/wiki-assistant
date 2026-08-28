/* WAIT on-wiki userscript (architecture §1.1). One file, loaded as a plain classic script —
 * no build step, no module system (MediaWiki gadgets/userscripts don't support ESM import).
 *
 * Rendering contract (#32, #37, architecture §9.2/§9.3/§9.8):
 *  - Model reply text is NEVER rendered as HTML. Always textContent, never innerHTML, never a
 *    markdown-to-HTML pipeline that could pass through raw tags.
 *  - No auto-linkification of URL-looking text found INSIDE the reply — even a real-looking
 *    URL in prose stays inert text. Only the API response's separate, pre-validated `links`
 *    array (already filtered server-side per §9.4) becomes real, clickable anchors.
 *  - Every code block gets its own visible, non-dismissible AI-suggested-code disclaimer —
 *    there is deliberately no collapse/hide affordance for it anywhere in this file.
 *
 * Split into two layers so the actual safety decisions are covered by DOM-free unit tests
 * (see WAIT.test.js) rather than only exercised by hand in a browser:
 *   - parseReplySegments / buildLinkDescriptors: pure functions, plain data in, plain data out.
 *   - renderReplySegments / renderLinks: thin DOM-application layer over that plain data.
 */

var CODE_FENCE_PATTERN = /```[^\n]*\n([\s\S]*?)```/g;

function parseReplySegments(replyText) {
  var segments = [];
  var lastIndex = 0;
  var match;

  CODE_FENCE_PATTERN.lastIndex = 0;
  while ((match = CODE_FENCE_PATTERN.exec(replyText)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        type: "text",
        value: replyText.slice(lastIndex, match.index),
      });
    }
    segments.push({ type: "code", value: match[1] });
    lastIndex = CODE_FENCE_PATTERN.lastIndex;
  }
  if (lastIndex < replyText.length) {
    segments.push({ type: "text", value: replyText.slice(lastIndex) });
  }
  return segments;
}

function isSafeHttpsUrl(rawUrl) {
  // Parse and check the actual scheme — never a substring/prefix check (the exact class of
  // bug architecture §9.4 warns about for the server-side allowlist applies here too: a naive
  // check can be bypassed in ways a real URL parse cannot). This is client-side defense in
  // depth: the server-side allowlist (#33) is the authoritative check, but the gadget must not
  // blindly trust an unvalidated href into the DOM regardless of what the server is supposed
  // to have already filtered — a `javascript:`/`data:` URL slipping through anywhere upstream
  // must still not become clickable here.
  try {
    return new URL(rawUrl).protocol === "https:";
  } catch {
    return false;
  }
}

function buildLinkDescriptors(links) {
  if (!Array.isArray(links)) {
    return [];
  }
  var descriptors = [];
  for (var i = 0; i < links.length; i += 1) {
    var link = links[i];
    if (
      link &&
      typeof link.url === "string" &&
      typeof link.title === "string" &&
      link.title.length > 0 &&
      isSafeHttpsUrl(link.url)
    ) {
      descriptors.push({ title: link.title, url: link.url });
    }
  }
  return descriptors;
}

var CODE_DISCLAIMER_TEXT =
  "AI-suggested code — review before use, especially before publishing to a shared gadget " +
  "or module.";

function renderReplySegments(doc, container, replyText) {
  var segments = parseReplySegments(replyText);
  for (var i = 0; i < segments.length; i += 1) {
    var segment = segments[i];
    if (segment.type === "code") {
      container.appendChild(buildCodeBlock(doc, segment.value));
    } else if (segment.value.length > 0) {
      container.appendChild(doc.createTextNode(segment.value));
    }
  }
}

function buildCodeBlock(doc, codeText) {
  var wrapper = doc.createElement("div");
  wrapper.className = "wait-code-block";

  var disclaimer = doc.createElement("p");
  disclaimer.className = "wait-code-disclaimer";
  disclaimer.appendChild(doc.createTextNode(CODE_DISCLAIMER_TEXT));
  wrapper.appendChild(disclaimer);

  var pre = doc.createElement("pre");
  var code = doc.createElement("code");
  code.appendChild(doc.createTextNode(codeText));
  pre.appendChild(code);
  wrapper.appendChild(pre);

  return wrapper;
}

function renderLinks(doc, container, links) {
  var descriptors = buildLinkDescriptors(links);
  for (var i = 0; i < descriptors.length; i += 1) {
    var descriptor = descriptors[i];
    var anchor = doc.createElement("a");
    anchor.href = descriptor.url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.appendChild(doc.createTextNode(descriptor.title));
    container.appendChild(anchor);
    container.appendChild(doc.createTextNode(" "));
  }
}

function renderReply(doc, container, response) {
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }
  renderReplySegments(
    doc,
    container,
    typeof response.reply === "string" ? response.reply : "",
  );
  if (Array.isArray(response.links) && response.links.length > 0) {
    var linksContainer = doc.createElement("div");
    linksContainer.className = "wait-links";
    renderLinks(doc, linksContainer, response.links);
    container.appendChild(linksContainer);
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    parseReplySegments: parseReplySegments,
    buildLinkDescriptors: buildLinkDescriptors,
    isSafeHttpsUrl: isSafeHttpsUrl,
    renderReply: renderReply,
    renderReplySegments: renderReplySegments,
    renderLinks: renderLinks,
    CODE_DISCLAIMER_TEXT: CODE_DISCLAIMER_TEXT,
  };
}
