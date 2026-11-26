import { Component, input } from '@angular/core';

@Component({
  selector: 'app-icon',
  template: `
    <svg
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.65"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      @switch (name()) {
        @case ('arrow') {
          <path d="M5 12h14m-6-6 6 6-6 6" />
        }
        @case ('chart') {
          <path d="M4 4v16h16M8 15l4-5 4 3 5-7" />
        }
        @case ('wallet') {
          <path d="M20 8V5a1 1 0 0 0-1-1H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h15V8H5a2 2 0 0 1 0-4" />
          <path d="M20 12h-5v4h5" />
        }
        @case ('target') {
          <circle cx="12" cy="12" r="9" />
          <circle cx="12" cy="12" r="5" />
          <circle cx="12" cy="12" r="1" />
        }
        @case ('branches') {
          <path d="M5 20v-6a3 3 0 0 1 3-3h8a3 3 0 0 0 3-3V4M12 20V4M16 7l3-3 3 3M9 7l3-3 3 3" />
        }
        @case ('shield') {
          <path d="m12 3 8 3v5c0 5-8 10-8 10S4 16 4 11V6l8-3Z" />
          <path d="m8 11 3 3 5-5" />
        }
        @case ('check') {
          <path d="m5 12 4 4L19 6" />
        }
        @case ('cookie') {
          <path d="M21 12a9 9 0 1 1-9-9 5 5 0 0 0 5 5 4 4 0 0 0 4 4Z" />
          <path d="M8 8h.01M7 14h.01M13 16h.01M12 11h.01" />
        }
        @case ('menu') {
          <path d="M4 6h16M4 12h16M4 18h16" />
        }
        @case ('close') {
          <path d="m6 6 12 12M6 18 18 6" />
        }
      }
    </svg>
  `,
})
export class Icon {
  readonly name = input.required<string>();
  readonly size = input(20);
}
