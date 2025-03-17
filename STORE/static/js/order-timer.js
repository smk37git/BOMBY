document.addEventListener('DOMContentLoaded', function() {
    const dueDateElement = document.getElementById('due-date');
    if (!dueDateElement) return;
    
    const dueDate = new Date(dueDateElement.dataset.date);
    
    function updateTimer() {
        const now = new Date();
        const diff = dueDate - now;
        
        if (diff <= 0) {
            document.getElementById('countdown').innerHTML = "Time's up!";
            return;
        }
        
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((diff % (1000 * 60)) / 1000);
        
        document.getElementById('countdown').innerHTML = 
            `${days}d ${hours}h ${minutes}m ${seconds}s`;
    }
    
    // Update timer every second
    updateTimer();
    setInterval(updateTimer, 1000);
});