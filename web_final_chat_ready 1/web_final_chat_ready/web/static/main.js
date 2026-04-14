// Kosárba gomb funkció
document.querySelectorAll('[data-add-to-cart]').forEach(button => {
    button.addEventListener('click', function() {
        const productId = this.getAttribute('data-product-id');
        const quantity = 1;
        
        fetch(`/add-to-cart/${productId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ quantity: quantity })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Termék hozzáadva a kosárhoz!');
            } else {
                alert('Hiba történt: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Hiba:', error);
            alert('Kérjük jelentkezzen be a kosárhoz való hozzáadáshoz.');
            window.location.href = '/login';
        });
    });
});