// Ensure the DOM is fully loaded before attaching event listeners
document.addEventListener('DOMContentLoaded', function() {

    // Handle the syllabus form submission
    document.getElementById('syllabus-form').addEventListener('submit', function(event) {
        event.preventDefault(); // Prevent the default form submission

        const formData = new FormData(this); // Create a FormData object from the form

        // Display a loading message or spinner if desired
        const resultsDiv = document.getElementById('results');
        resultsDiv.innerHTML = "Generating questions, please wait...";
        document.getElementById('generate-papers').disabled = true; // Disable the button initially

        fetch('/generate-questions', {
            method: 'POST',
            body: formData // Send the form data
        })
        .then(response => {
            if (!response.ok) {
                // Attempt to parse the error message from the response
                return response.json().then(err => { throw err; });
            }
            return response.json(); 
        })
        .then(data => {
            if (data.message) {
                // Display the success message
                let htmlContent = `<p>${data.message}</p>`;

                // Optionally, display the list of units
                if (data.units && Array.isArray(data.units) && data.units.length > 0) {
                    htmlContent += `<h3>Units Processed:</h3><ol>`;
                    data.units.forEach(unit => {
                        htmlContent += `<li>${unit}</li>`;
                    });
                    htmlContent += `</ol>`;
                }

                resultsDiv.innerHTML = htmlContent;

                // Enable the "Generate Question Papers" button
                document.getElementById('generate-papers').disabled = false;
            } else if (data.error) {
                // Display the error message from the response
                resultsDiv.innerHTML = `<p style="color: red;">Error: ${data.error}</p>`;
                console.error("Error response:", data);
                // Ensure the "Generate Question Papers" button is disabled
                document.getElementById('generate-papers').disabled = true;
            } else {
                // Handle unexpected response formats
                resultsDiv.innerHTML = `<p style="color: red;">Error: Unexpected response format.</p>`;
                console.error("Unexpected response:", data);
                // Ensure the "Generate Question Papers" button is disabled
                document.getElementById('generate-papers').disabled = true;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            // Display a user-friendly error message
            const errorMessage = error.error || error.message || 'Unknown error.';
            resultsDiv.innerHTML = `<p style="color: red;">An error occurred: ${errorMessage}</p>`;
            // Disable the "Generate Question Papers" button to prevent further actions
            document.getElementById('generate-papers').disabled = true;
        });
    });

    // Handle the "Generate Question Papers" button click
    document.getElementById('generate-papers').addEventListener('click', function() {
        const generateButton = this;
        generateButton.disabled = true; // Disable the button to prevent multiple clicks

        // Optionally, display a loading message or spinner
        const downloadLinksDiv = document.getElementById('download-links');
        downloadLinksDiv.innerHTML = "Generating question papers, please wait...";

        fetch('/generate-papers')
        .then(response => {
            if (!response.ok) {
                // Attempt to parse the error message from the response
                return response.json().then(err => { throw err; });
            }
            return response.json();
        })
        .then(data => {
            if (data.papers && Array.isArray(data.papers) && data.papers.length > 0) {
                downloadLinksDiv.innerHTML = ''; // Clear previous links or messages

                // Create and append download links for each generated paper
                data.papers.forEach((paper, index) => {
                    const link = document.createElement('a');
                    link.href = `/download/${encodeURIComponent(paper)}`;
                    link.textContent = `Download Question Paper ${index + 1}`;
                    link.download = paper;

                    // Optional: Add some styling or line breaks
                    link.style.display = 'block';
                    link.style.marginBottom = '10px';

                    downloadLinksDiv.appendChild(link);
                });

                // Display a success message
                const successMsg = document.createElement('p');
                successMsg.textContent = data.message || "All question papers have been generated successfully!";
                downloadLinksDiv.prepend(successMsg);
            } else if (data.error) {
                // Display the error message from the response
                downloadLinksDiv.innerHTML = `<p style="color: red;">Error: ${data.error}</p>`;
                console.error("Error response:", data);
                // Re-enable the "Generate Question Papers" button to allow retry
                generateButton.disabled = false;
            } else {
                // Handle unexpected response formats
                downloadLinksDiv.innerHTML = `<p style="color: red;">Error: Unexpected response format.</p>`;
                console.error("Unexpected response:", data);
                // Re-enable the "Generate Question Papers" button to allow retry
                generateButton.disabled = false;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            // Display a user-friendly error message
            const errorMessage = error.error || error.message || 'Unknown error.';
            downloadLinksDiv.innerHTML = `<p style="color: red;">An error occurred: ${errorMessage}</p>`;
            // Re-enable the "Generate Question Papers" button to allow retry
            generateButton.disabled = false;
        });
    });

});
