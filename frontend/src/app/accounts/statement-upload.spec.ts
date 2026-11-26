import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { StatementUpload } from './statement-upload';

describe('StatementUpload', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [StatementUpload], providers: [provideHttpClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); TestBed.resetTestingModule(); });
  it('sends the selected account and PDF once and reports saved transactions', () => {
    const fixture = TestBed.createComponent(StatementUpload), page = fixture.componentInstance;
    fixture.componentRef.setInput('account', { id: 1, name: 'Bank', currency: 'UAH' });
    const file = new File(['%PDF-test'], 'statement.pdf', { type: 'application/pdf' });
    page.choose({ target: { files: [file] } } as unknown as Event);
    page.analyze(); page.analyze();
    const request = http.expectOne('/api/statements/import');
    expect(request.request.method).toBe('POST');
    expect((request.request.body as FormData).get('file')).toBe(file);
    expect((request.request.body as FormData).get('account_id')).toBe('1');
    request.flush({ imported_count: 2, duplicate: false });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Збережено операцій: 2');
    expect(page.pending()).toBe(false); fixture.destroy();
  });
  it('rejects unsupported files and allows retry after provider failure', () => {
    const fixture = TestBed.createComponent(StatementUpload), page = fixture.componentInstance;
    fixture.componentRef.setInput('account', { id: 1, name: 'Bank', currency: 'UAH' });
    page.choose({ target: { files: [new File(['x'], 'file.csv')] } } as unknown as Event);
    page.analyze(); http.expectNone('/api/statements/import');
    expect(page.error()).toBeTruthy();
    page.choose({ target: { files: [new File(['%PDF-test'], 'file.pdf')] } } as unknown as Event);
    page.analyze(); http.expectOne('/api/statements/import').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(page.pending()).toBe(false); expect(page.notice()).toBe('');
    expect(page.error()).toContain('недоступний'); fixture.destroy();
  });
});
