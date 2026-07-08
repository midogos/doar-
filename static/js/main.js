// Micro-interação simples: feedback visual ao clicar em botões
document.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("mousedown", () => {
        btn.style.transform = "scale(0.97)";
    });
    ["mouseup", "mouseleave"].forEach((evt) => {
        btn.addEventListener(evt, () => {
            btn.style.transform = "scale(1)";
        });
    });
});
