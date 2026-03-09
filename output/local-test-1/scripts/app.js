document.addEventListener('DOMContentLoaded', () => {
    const billAmountInput = document.getElementById('bill-amount');
    const participantForm = document.getElementById('participant-form');
    const participantNameInput = document.getElementById('participant-name');
    const participantEmailInput = document.getElementById('participant-email');
    const participantList = document.getElementById('participant-list');
    const evenSplitButton = document.getElementById('even-split');
    const customSplitButton = document.getElementById('custom-split');
    const itemizedSplitButton = document.getElementById('itemized-split');
    const taxPercentageInput = document.getElementById('tax-percentage');
    const tipPercentageInput = document.getElementById('tip-percentage');
    const summaryView = document.getElementById('summary-view');
    const finalizeButton = document.getElementById('finalize');
    const resetButton = document.getElementById('reset');

    const state = {
        billTotal: parseFloat(localStorage.getItem('billTotal')) || 0,
        taxPercent: parseFloat(localStorage.getItem('taxPercent')) || 0,
        tipPercent: parseFloat(localStorage.getItem('tipPercent')) || 0,
        participants: JSON.parse(localStorage.getItem('participants')) || []
    };

    function updateLocalStorage() {
        localStorage.setItem('billTotal', state.billTotal);
        localStorage.setItem('taxPercent', state.taxPercent);
        localStorage.setItem('tipPercent', state.tipPercent);
        localStorage.setItem('participants', JSON.stringify(state.participants));
    }

    function render() {
        billAmountInput.value = state.billTotal || '';
        taxPercentageInput.value = state.taxPercent || '';
        tipPercentageInput.value = state.tipPercent || '';

        participantList.innerHTML = '';
        state.participants.forEach(({ name, email, shareAmount, id }) => {
            const li = document.createElement('li');
            li.textContent = `${name} (${email || 'No email'}) - Share: $${shareAmount.toFixed(2)}`;
            li.dataset.id = id;
            participantList.appendChild(li);
        });

        const totalCost = state.billTotal + (state.billTotal * state.taxPercent / 100) + (state.billTotal * state.tipPercent / 100);
        summaryView.textContent = `Total Split Cost: $${totalCost.toFixed(2)}`;
    }

    async function addParticipant(e) {
        e.preventDefault();
        const name = participantNameInput.value.trim();
        const email = participantEmailInput.value.trim();

        if (name) {
            const newParticipant = {
                name,
                email,
                shareAmount: 0,
                id: crypto.randomUUID()
            };
            state.participants.push(newParticipant);
            participantNameInput.value = '';
            participantEmailInput.value = '';
            updateLocalStorage();
            render();
        }
    }

    participantForm.addEventListener('submit', addParticipant);

    function resetApp() {
        state.billTotal = 0;
        state.taxPercent = 0;
        state.tipPercent = 0;
        state.participants = [];
        updateLocalStorage();
        render();
    }

    function finalizeDetails() {
        render();
    }

    resetButton.addEventListener('click', resetApp);
    finalizeButton.addEventListener('click', finalizeDetails);

    render();
});