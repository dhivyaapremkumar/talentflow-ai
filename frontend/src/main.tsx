import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './styles/global.css';
import App from './App.tsx';
import { ActorProvider } from './context/ActorContext';
import { ToastProvider } from './context/ToastContext';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ActorProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </ActorProvider>
    </BrowserRouter>
  </StrictMode>,
);
