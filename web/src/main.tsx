import React from 'react';
import ReactDOM from 'react-dom/client';
import './fonts.css';

import './styles.css';
import { App } from './App';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
if ('serviceWorker' in navigator && import.meta.env.PROD) window.addEventListener('load',()=>{navigator.serviceWorker.register('./sw.js').catch(()=>{/* Health still derives from the verified bundle. */});});
