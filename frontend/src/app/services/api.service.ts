import { Injectable, NgZone } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';


@Injectable({
    providedIn: 'root'
})
export class APIService {

    private readonly baseUrl = 'http://localhost:5000';

    constructor(private http: HttpClient,private zone: NgZone) { }

    getData(endpoint: string, params?: { [key: string]: string }): Observable<any> {
        let httpParams = new HttpParams();
        if (params) {
            for (const key in params) {
                if (params.hasOwnProperty(key)) {
                    httpParams = httpParams.set(key, params[key]);
                }
            }
        }
        return this.http.get(`${this.baseUrl}/${endpoint}`, { params: httpParams, withCredentials: true });
    }

    postData(endpoint: string, data: any): Observable<any> {
        return this.http.post(`${this.baseUrl}/${endpoint}`, data, { withCredentials: true });
    }

    streamPostData(endpoint: string, data: any): Observable<any> {
        return new Observable(observer => {
            const controller = new AbortController();

            fetch(`${this.baseUrl}/${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
                signal: controller.signal,
                credentials: 'include'
            }).then(async response => {
                if (!response.body) throw new Error('ReadableStream not supported.');

                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n\n');
                    buffer = lines.pop() || ''; // Keep the incomplete line in the buffer

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.substring(6);
                            try {
                                const data = JSON.parse(dataStr);
                                // Ensure UI updates run inside Angular's zone
                                this.zone.run(() => observer.next(data));
                            } catch (e) {
                                console.error('Error parsing stream data', e);
                            }
                        }
                    }
                }
                this.zone.run(() => observer.complete());
            }).catch((err:any) => {
                if (err.name !== 'AbortError') {
                    this.zone.run(() => observer.error(err));
                }
            });

            // Cleanup if the component unmounts or unsubscribes
            return () => controller.abort();
        });
    }
}
