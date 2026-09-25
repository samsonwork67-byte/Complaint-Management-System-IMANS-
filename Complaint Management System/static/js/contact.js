document.getElementById('contactForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const name = document.getElementById('contactName').value;
    const email = document.getElementById('contactEmail').value;
    const message = document.getElementById('contactMessage').value;

    console.log({ name, email, message });

    const res = await fetch("http://127.0.0.1:5000/api/contact", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ name, email, message })
    });

    const data = await res.json();

    if (res.ok) {
        alert("Message sent successfully!");
        e.target.reset();
    } else {
        alert(data.error || "Failed to send message");
    }
});

