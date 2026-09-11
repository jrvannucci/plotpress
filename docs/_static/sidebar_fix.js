// Removes a Sphinx toctree-resolution artifact from the RTD sidebar: with
// sphinx-gallery's "nested_sections" mode (the current default), each
// multi-subsection gallery's own generated index.rst carries a
// `.. toctree:: :hidden: :includehidden:` listing its own subsections --
// deliberately, so the sidebar can walk into it (see custom.css's own
// comment on why "Finance, economics and risk" et al. render as a plain
// `<a href="...#finance-economics-and-risk">` sidebar entry rather than a
// distinct page). But Sphinx's own toctree resolution, given that
// `:includehidden:`, sometimes re-attaches OTHER entries from that same
// sibling list as if they were children of one particular entry, and not
// always the same way: "Finance, economics and risk" (the *last*
// subsection in "Real applications") gets its *entire* 19-item sibling
// list duplicated underneath it (still visible, alongside its own correct
// top-level entry); "Custom interactive JS" (mid-list, in the example
// gallery) is worse -- it picks up the two items immediately after it
// ("Polar", "Signal processing") as bogus children, and those two are
// MISSING their own top-level sidebar entry entirely, reachable nowhere
// else in the sidebar. Confirmed directly across every multi-subsection
// gallery; there is nothing in this project's own gallery structure that
// lists a subsection's siblings as its children or drops one out of the
// top-level list -- every occurrence found is this same Sphinx artifact.
//
// CSS alone can catch the "duplicated, made of real separate-page links"
// shape (see custom.css), but not the "stolen, anchor-only" shape here --
// its bogus children look structurally identical to a genuinely nested
// single-page TOC (e.g. api.html's own "Figure" -> "Figure()"/"subplots()",
// or user_guide/limitations.html's own section list). What actually tells
// a gallery's bogus nesting apart from a real one isn't structure, it's
// which top-level sidebar caption an entry lives under: every gallery
// subsection is deliberately kept to "one click away, from its index
// page's own thumbnails" (see custom.css) and never legitimately shows a
// nested list of its own in the sidebar at all, whereas a caption like
// "Reference" or "Limitations" wraps one real, single, long page whose own
// section list is exactly the useful nested TOC a reader wants. So: within
// a known gallery caption, ANY subsection anchor's nested list is dropped
// unconditionally. "Polar"/"Signal processing" et al. still don't get
// their own top-level sidebar entry back -- that would mean synthesizing
// DOM Sphinx never rendered in the first place, past what a page script
// should take on -- but they're at least reachable again from their
// gallery's own index page thumbnails, rather than sitting in the sidebar
// nested under an unrelated sibling where a reader would never think to
// look for them.
(function () {
  // Matches docs/index.rst's own top-level `:caption:` values for every
  // toctree that points at a sphinx-gallery output directory. Deliberately
  // NOT "Reference"/"Limitations"/"Getting started"/"User guide" -- those
  // wrap a single real page whose own nested anchors are wanted.
  var GALLERY_CAPTIONS = ["Examples", "Live plotting", "Real applications"];

  function captionFor(topLevelUl) {
    var node = topLevelUl.previousElementSibling;
    while (node && !node.classList.contains("caption")) {
      node = node.previousElementSibling;
    }
    return node ? node.textContent.trim() : null;
  }

  function pruneSidebarArtifacts() {
    var menu = document.querySelector(".wy-menu-vertical");
    if (!menu) return;
    // Only the <ul> elements Sphinx renders as direct children of the menu
    // are "top-level" -- each is the one caption's own toctree.
    Array.prototype.forEach.call(menu.children, function (topLevelUl) {
      if (topLevelUl.tagName !== "UL") return;
      var isGallery = GALLERY_CAPTIONS.indexOf(captionFor(topLevelUl)) !== -1;
      topLevelUl.querySelectorAll("li").forEach(function (li) {
        var ownLink = li.querySelector(":scope > a");
        var nestedList = li.querySelector(":scope > ul");
        if (!ownLink || !nestedList) return;
        var href = ownLink.getAttribute("href") || "";
        var isSubsectionAnchor = href.indexOf("#") !== -1 && href !== "#";
        if (isGallery && isSubsectionAnchor) {
          nestedList.style.display = "none";
          return;
        }
        // Outside a gallery caption (or for a real-page entry inside one),
        // fall back to detecting an exact duplicate of one of this entry's
        // own siblings -- the general form of the "Finance"/"Limitations"
        // shape, kept as a safety net for any occurrence CSS doesn't reach.
        var parentList = li.parentElement;
        if (!parentList || parentList.tagName !== "UL") return;
        var siblingTexts = new Set();
        parentList.querySelectorAll(":scope > li > a").forEach(function (sibling) {
          if (sibling !== ownLink) siblingTexts.add(sibling.textContent.trim());
        });
        var isDuplicated = Array.prototype.some.call(
          nestedList.querySelectorAll(":scope > li > a"),
          function (child) { return siblingTexts.has(child.textContent.trim()); }
        );
        if (isDuplicated) nestedList.style.display = "none";
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", pruneSidebarArtifacts);
  } else {
    pruneSidebarArtifacts();
  }
})();
