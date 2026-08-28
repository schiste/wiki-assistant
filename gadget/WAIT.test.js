const test = require("node:test");
const assert = require("node:assert");
const {
  parseReplySegments,
  buildLinkDescriptors,
  isSafeHttpsUrl,
  renderReply,
  CODE_DISCLAIMER_TEXT,
} = require("./WAIT.js");

// Minimal fake DOM: just enough surface for these tests, not a general-purpose
// implementation. Proves the actual safety property (text nodes hold literal strings,
// never parsed as markup) without adding a jsdom-style dependency for one file.
function createFakeDocument() {
  function FakeNode(kind) {
    this.kind = kind;
    this.children = [];
    this.attributes = {};
  }

  FakeNode.prototype.appendChild = function (child) {
    this.children.push(child);
    return child;
  };

  FakeNode.prototype.removeChild = function (child) {
    var index = this.children.indexOf(child);
    if (index !== -1) {
      this.children.splice(index, 1);
    }
    return child;
  };

  Object.defineProperty(FakeNode.prototype, "firstChild", {
    get: function () {
      return this.children.length > 0 ? this.children[0] : null;
    },
  });

  Object.defineProperty(FakeNode.prototype, "textContent", {
    get: function () {
      if (this.kind === "text") {
        return this.data;
      }
      return this.children.map((child) => child.textContent).join("");
    },
  });

  return {
    createElement: function (tagName) {
      var node = new FakeNode("element");
      node.tagName = tagName;
      return node;
    },
    createTextNode: function (data) {
      var node = new FakeNode("text");
      node.data = data;
      return node;
    },
  };
}

function findByTag(node, tagName) {
  var results = [];
  (function walk(current) {
    if (current.kind === "element" && current.tagName === tagName) {
      results.push(current);
    }
    for (var i = 0; i < current.children.length; i += 1) {
      walk(current.children[i]);
    }
  })(node);
  return results;
}

function findByClassName(node, className) {
  var results = [];
  (function walk(current) {
    if (current.kind === "element" && current.className === className) {
      results.push(current);
    }
    for (var i = 0; i < current.children.length; i += 1) {
      walk(current.children[i]);
    }
  })(node);
  return results;
}

test("parseReplySegments: plain text with no code fences is one text segment", () => {
  const segments = parseReplySegments("just some prose");

  assert.deepStrictEqual(segments, [
    { type: "text", value: "just some prose" },
  ]);
});

test("parseReplySegments: a single fenced code block is isolated as its own segment", () => {
  const segments = parseReplySegments(
    "before\n```js\nconst x = 1;\n```\nafter",
  );

  assert.deepStrictEqual(segments, [
    { type: "text", value: "before\n" },
    { type: "code", value: "const x = 1;\n" },
    { type: "text", value: "\nafter" },
  ]);
});

test("parseReplySegments: multiple fenced code blocks each become their own segment", () => {
  const segments = parseReplySegments("```a\none\n```\nmiddle\n```b\ntwo\n```");

  assert.deepStrictEqual(segments, [
    { type: "code", value: "one\n" },
    { type: "text", value: "\nmiddle\n" },
    { type: "code", value: "two\n" },
  ]);
});

test("buildLinkDescriptors: passes through well-formed entries", () => {
  const descriptors = buildLinkDescriptors([
    { title: "Article", url: "https://fr.wikipedia.org/wiki/Article" },
  ]);

  assert.deepStrictEqual(descriptors, [
    { title: "Article", url: "https://fr.wikipedia.org/wiki/Article" },
  ]);
});

test("buildLinkDescriptors: filters out entries missing a title or url", () => {
  const descriptors = buildLinkDescriptors([
    { title: "Has both", url: "https://fr.wikipedia.org/wiki/X" },
    { title: "", url: "https://fr.wikipedia.org/wiki/Y" },
    { url: "https://fr.wikipedia.org/wiki/Z" },
    { title: "No url" },
    null,
  ]);

  assert.deepStrictEqual(descriptors, [
    { title: "Has both", url: "https://fr.wikipedia.org/wiki/X" },
  ]);
});

test("buildLinkDescriptors: non-array input returns an empty list", () => {
  assert.deepStrictEqual(buildLinkDescriptors(undefined), []);
  assert.deepStrictEqual(buildLinkDescriptors(null), []);
});

test("isSafeHttpsUrl: accepts a well-formed https URL", () => {
  assert.strictEqual(
    isSafeHttpsUrl("https://fr.wikipedia.org/wiki/Article"),
    true,
  );
});

test("isSafeHttpsUrl: rejects javascript: URLs", () => {
  assert.strictEqual(isSafeHttpsUrl("javascript:alert(1)"), false);
});

test("isSafeHttpsUrl: rejects data: URLs", () => {
  assert.strictEqual(
    isSafeHttpsUrl("data:text/html,<script>alert(1)</script>"),
    false,
  );
});

test("isSafeHttpsUrl: rejects plain http (not https)", () => {
  assert.strictEqual(
    isSafeHttpsUrl("http://fr.wikipedia.org/wiki/Article"),
    false,
  );
});

test("isSafeHttpsUrl: rejects a value that fails to parse as a URL at all", () => {
  assert.strictEqual(isSafeHttpsUrl("not a url"), false);
  assert.strictEqual(isSafeHttpsUrl(""), false);
});

test("buildLinkDescriptors: drops entries whose URL is not https", () => {
  const descriptors = buildLinkDescriptors([
    { title: "Safe", url: "https://fr.wikipedia.org/wiki/Safe" },
    { title: "Malicious", url: "javascript:alert(document.cookie)" },
    {
      title: "Also malicious",
      url: "data:text/html,<script>alert(1)</script>",
    },
  ]);

  assert.deepStrictEqual(descriptors, [
    { title: "Safe", url: "https://fr.wikipedia.org/wiki/Safe" },
  ]);
});

test("renderReply: a javascript: URL never becomes a clickable anchor href", () => {
  const doc = createFakeDocument();
  const container = doc.createElement("div");

  renderReply(doc, container, {
    reply: "click below",
    links: [{ title: "Looks safe", url: "javascript:alert(document.cookie)" }],
  });

  assert.strictEqual(findByTag(container, "a").length, 0);
});

test("renderReply: a script-tag-looking reply renders as inert literal text, never HTML", () => {
  const doc = createFakeDocument();
  const container = doc.createElement("div");
  const payload = '<script>alert(1)</script> and <img onerror="alert(2)">';

  renderReply(doc, container, { reply: payload, links: [] });

  // No real element was created for the payload — it exists only as text-node data.
  assert.strictEqual(findByTag(container, "script").length, 0);
  assert.strictEqual(findByTag(container, "img").length, 0);
  assert.strictEqual(container.textContent, payload);
});

test("renderReply: a URL appearing in prose is never auto-linkified", () => {
  const doc = createFakeDocument();
  const container = doc.createElement("div");

  renderReply(doc, container, {
    reply: "See https://fr.wikipedia.org/wiki/Something for details.",
    links: [],
  });

  assert.strictEqual(findByTag(container, "a").length, 0);
  assert.ok(
    container.textContent.indexOf("https://fr.wikipedia.org/wiki/Something") !==
      -1,
  );
});

test("renderReply: every code block gets its own non-removable disclaimer", () => {
  const doc = createFakeDocument();
  const container = doc.createElement("div");

  renderReply(doc, container, {
    reply: "```js\nfirst();\n```\ntext between\n```js\nsecond();\n```",
    links: [],
  });

  const disclaimers = findByClassName(container, "wait-code-disclaimer");
  assert.strictEqual(disclaimers.length, 2);
  for (const disclaimer of disclaimers) {
    assert.strictEqual(disclaimer.textContent, CODE_DISCLAIMER_TEXT);
  }
  const codeBlocks = findByTag(container, "code");
  assert.deepStrictEqual(
    codeBlocks.map((node) => node.textContent),
    ["first();\n", "second();\n"],
  );
});

test("renderReply: pre-validated links render as real, safe anchors", () => {
  const doc = createFakeDocument();
  const container = doc.createElement("div");

  renderReply(doc, container, {
    reply: "see the link",
    links: [
      { title: "Wikipedia article", url: "https://fr.wikipedia.org/wiki/Foo" },
    ],
  });

  const anchors = findByTag(container, "a");
  assert.strictEqual(anchors.length, 1);
  assert.strictEqual(anchors[0].href, "https://fr.wikipedia.org/wiki/Foo");
  assert.strictEqual(anchors[0].rel, "noopener noreferrer");
  assert.strictEqual(anchors[0].target, "_blank");
  assert.strictEqual(anchors[0].textContent, "Wikipedia article");
});

test("renderReply: clears any previously rendered content before rendering again", () => {
  const doc = createFakeDocument();
  const container = doc.createElement("div");

  renderReply(doc, container, { reply: "first response", links: [] });
  renderReply(doc, container, { reply: "second response", links: [] });

  assert.strictEqual(container.textContent, "second response");
});
