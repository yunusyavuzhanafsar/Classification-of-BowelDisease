const email = document.querySelector('input[name="email"]').value;
const password = document.querySelector('input[name="password"]').value;


if (emailInput && passwordInput) {
  const email = emailInput.value;
  const password = passwordInput.value;

  if (!email || !password) {
    alert("Lütfen tüm alanları doldurun.");
    return;
  }
}
