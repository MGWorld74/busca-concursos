/* Service worker do Firebase Cloud Messaging.
   Precisa ficar na raiz do site (mesmo nível do index.html) para que o
   registro em "./firebase-messaging-sw.js" tenha escopo sobre todo o site. */
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyAzdlivqw9Bm2jl-hYtr0DaisdQ3zrP2h8",
  authDomain: "alertaconcurso-7e456.firebaseapp.com",
  projectId: "alertaconcurso-7e456",
  storageBucket: "alertaconcurso-7e456.firebasestorage.app",
  messagingSenderId: "609357356859",
  appId: "1:609357356859:web:0098178f08df84a0bde11e",
  measurementId: "G-CMWQVCDNMM"
});

const messaging = firebase.messaging();

// Notificações recebidas com o site em segundo plano (ou fechado) passam por aqui.
messaging.onBackgroundMessage((payload) => {
  const n = payload.notification || {};
  const link = (payload.fcmOptions && payload.fcmOptions.link)
    || (payload.data && payload.data.link)
    || './';
  self.registration.showNotification(n.title || 'Novo concurso', {
    body: n.body || '',
    icon: 'radar-concursos-banner.jpg',
    data: { link }
  });
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const link = (event.notification.data && event.notification.data.link) || './';
  event.waitUntil(clients.openWindow(link));
});
