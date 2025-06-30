document.getElementById('syllabus-form').addEventListener('submit', function(event) {
    event.preventDefault(); // Prevent the default form submission

    const formData = new FormData(this); // Create a FormData object from the form

    fetch('/generate-questions', {
        method: 'POST',
        body: formData // Send the form data
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok: ' + response.statusText);
        }
        return response.json(); 
    })
    .then(data => {
        if (data.questions && Array.isArray(data.questions)) {
            // Display the generated questions
            const questionsList = data.questions.map(question => `<li>${question}</li>`).join('');
            document.getElementById('results').innerHTML = `<ol>${questionsList}</ol>`;

            // Enable the "Generate Question Papers" button
            document.getElementById('generate-papers').disabled = false;
        } else {
            document.getElementById('results').innerHTML = "Error: Unexpected response format.";
        }
    })
    .catch(error => {
        console.error('Error:', error);
        document.getElementById('results').innerHTML = "An error occurred: " + error.message;
    });
});

document.getElementById('generate-papers').addEventListener('click', function() {
    this.disabled = true; // Disable the button to prevent multiple clicks

    fetch('/generate-papers')
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        if (data.papers && Array.isArray(data.papers)) {
            const downloadLinksDiv = document.getElementById('download-links');
            downloadLinksDiv.innerHTML = ''; // Clear previous links

            data.papers.forEach((paper, index) => {
                const link = document.createElement('a');
                link.href = `/download/${paper}`;
                link.textContent = `Download Question Paper ${index + 1}`;
                link.download = paper;
                downloadLinksDiv.appendChild(link);
                downloadLinksDiv.appendChild(document.createElement('br'));
            });
        } else {
            document.getElementById('results').innerHTML = "Error: Unexpected response format.";
        }
    })
    .catch(error => {
        console.error('Error:', error);
        document.getElementById('generate-papers').disabled = false; // Re-enable the button in case of an error
        document.getElementById('results').innerHTML = "An error occurred: " + error.message;
    });
});
