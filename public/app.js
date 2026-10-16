const cards = [...document.querySelectorAll(".product-card")];
const countEl = document.getElementById("cart-count");
const selectionList = document.getElementById("selection-list");
const emptyState = document.getElementById("selection-empty");
const totalEl = document.getElementById("estimated-total");
const responseBox = document.getElementById("server-response");
const submitBtn = document.getElementById("submit-btn");
const searchInput = document.getElementById("search-input");
const clearSearch = document.getElementById("clear-search");
const resultCount = document.getElementById("result-count");
const noResults = document.getElementById("no-results");
let activeCategory = "All";

function getQty(card) { return Number(card.querySelector(".qty").textContent) || 0; }
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  }[char]));
}
function updateSelection() {
  const selected = cards.map(card => ({
    quantity: getQty(card),
    id: card.dataset.productId,
    code: card.dataset.code,
    name: card.querySelector("h3").textContent,
    price: Number(card.querySelector(".product-bottom strong").textContent.replace(/[₹,]/g, "")),
    unit: card.querySelector(".unit-label").textContent
  })).filter(item => item.quantity > 0);

  const totalQty = selected.reduce((sum, item) => sum + item.quantity, 0);
  const total = selected.reduce((sum, item) => sum + item.price * item.quantity, 0);
  countEl.textContent = totalQty;
  totalEl.textContent = `₹${total.toLocaleString("en-IN")}`;
  emptyState.hidden = selected.length > 0;
  selectionList.innerHTML = selected.map(item =>
    `<div class="selection-row"><span><b>${escapeHtml(item.name)}</b><small>Code ${escapeHtml(item.code)} · ${escapeHtml(item.unit)} × ${item.quantity}</small></span><span>₹${(item.price * item.quantity).toLocaleString("en-IN")}</span></div>`
  ).join("");
}
function filterProducts() {
  const query = searchInput.value.trim().toLowerCase();
  let visible = 0;
  cards.forEach(card => {
    const matchesCategory = activeCategory === "All" || card.dataset.category === activeCategory;
    const matchesQuery = !query || card.dataset.name.includes(query) || card.dataset.code.toLowerCase().includes(query);
    const show = matchesCategory && matchesQuery;
    card.hidden = !show;
    if (show) visible++;
  });
  resultCount.textContent = `Showing ${visible} of ${cards.length} products`;
  noResults.hidden = visible !== 0;
}
cards.forEach(card => {
  card.querySelector(".minus").addEventListener("click", () => {
    const qty = card.querySelector(".qty");
    qty.textContent = Math.max(0, getQty(card) - 1);
    updateSelection();
  });
  card.querySelector(".plus").addEventListener("click", () => {
    const qty = card.querySelector(".qty");
    qty.textContent = Math.min(100, getQty(card) + 1);
    updateSelection();
  });
});
document.querySelectorAll(".category-chip").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".category-chip").forEach(b => b.classList.remove("active"));
    button.classList.add("active");
    activeCategory = button.dataset.category;
    filterProducts();
  });
});
searchInput.addEventListener("input", filterProducts);
clearSearch.addEventListener("click", () => {
  searchInput.value = "";
  filterProducts();
  searchInput.focus();
});
document.querySelectorAll(".nav-item").forEach(link => {
  link.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
    link.classList.add("active");
  });
});
document.getElementById("order-form").addEventListener("submit", async event => {
  event.preventDefault();
  responseBox.hidden = true;
  responseBox.classList.remove("error");
  const items = cards.map(card => ({product_id: card.dataset.productId, quantity: getQty(card)}))
    .filter(item => item.quantity > 0);
  if (!items.length) {
    responseBox.textContent = "Please add at least one product before sending your selection.";
    responseBox.classList.add("error");
    responseBox.hidden = false;
    return;
  }
  const payload = {
    customer_name: document.getElementById("customer-name").value.trim(),
    phone: document.getElementById("phone").value.trim(),
    items
  };
  submitBtn.disabled = true;
  submitBtn.textContent = "Sending…";
  try {
    const response = await fetch("/api/orders", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result.message || "Could not send your selection.");
    const binary = atob(result.pdf_base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const pdfBlob = new Blob([bytes], {type: "application/pdf"});
    const pdfUrl = URL.createObjectURL(pdfBlob);
    const downloadLink = document.createElement("a");
    downloadLink.href = pdfUrl;
    downloadLink.download = result.pdf_filename || "order.pdf";
    document.body.appendChild(downloadLink);
    downloadLink.click();
    downloadLink.remove();
    setTimeout(() => URL.revokeObjectURL(pdfUrl), 30000);
    responseBox.innerHTML = `<strong>${escapeHtml(result.message)}</strong><br>Reference: ${escapeHtml(result.order.order_id)}<br>Estimated total: ₹${Number(result.order.total).toLocaleString("en-IN")}<br><span class="pdf-download">Your PDF download should begin automatically.</span><br><small>${escapeHtml(result.order.status)}</small>`;
    cards.forEach(card => card.querySelector(".qty").textContent = "0");
    updateSelection();
    document.getElementById("order-form").reset();
  } catch (error) {
    responseBox.textContent = error.message || "Could not connect to the server. Please try again.";
    responseBox.classList.add("error");
  } finally {
    responseBox.hidden = false;
    submitBtn.disabled = false;
    submitBtn.innerHTML = 'Send selection to stall <span>→</span>';
  }
});
updateSelection();
filterProducts();
