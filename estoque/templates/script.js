<script>
document.addEventListener("DOMContentLoaded", () => {
    const cards = document.querySelectorAll(".animate-card");
    cards.forEach((card, i) => {
        setTimeout(() => {
            card.classList.add("show");
        }, i * 150);
    });
});
</script>