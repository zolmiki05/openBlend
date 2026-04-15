import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { providePrimeNG } from 'primeng/config';
import { definePreset } from '@primeng/themes';
import Aura from '@primeng/themes/aura';
import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';

const SpotifyPreset = definePreset(Aura, {
  semantic: {
    primary: {
      50:  '#e8f8ee',
      100: '#c8f0d7',
      200: '#9de0b5',
      300: '#6cce90',
      400: '#44bf72',
      500: '#1DB954',
      600: '#179e47',
      700: '#11823a',
      800: '#0b672e',
      900: '#064c21',
      950: '#023314',
    },
  },
});

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([authInterceptor])),
    providePrimeNG({
      theme: {
        preset: SpotifyPreset,
        options: {
          darkModeSelector: false,
          cssLayer: false,
        },
      },
    }),
  ],
};
