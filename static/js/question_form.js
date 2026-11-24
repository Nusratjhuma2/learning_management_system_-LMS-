/* ===== QUESTION FORM PAGE JS ===== */
function toggleQuestionFields(type) {
    var choices = document.getElementById('choices-container');
    var tf = document.getElementById('tf-container');
    var sa = document.getElementById('short-answer-container');

    if (choices) choices.classList.add('d-none');
    if (tf) tf.classList.add('d-none');
    if (sa) sa.classList.add('d-none');

    if (type === 'single_choice' || type === 'multiple_choice') {
        if (choices) choices.classList.remove('d-none');
    } else if (type === 'true_false') {
        if (tf) tf.classList.remove('d-none');
    } else if (type === 'short_answer') {
        if (sa) sa.classList.remove('d-none');
    }
}

window.toggleQuestionFields = toggleQuestionFields;

document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var questionTypeSelect = document.getElementById('id_question_type');
    if (questionTypeSelect) {
        questionTypeSelect.addEventListener('change', function () {
            toggleQuestionFields(this.value);
        });
        toggleQuestionFields(questionTypeSelect.value);
    }
});
