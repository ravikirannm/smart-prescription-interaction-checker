import { ChangeDetectorRef, Component } from '@angular/core';
import { APIService } from '../../services/api.service';
import { FormControl } from '@angular/forms';
import { ICD11Result, InteractionResult, PseudoscienceFlag, PubmedResult, SourceLink, SymptomAnalysis, VerifiedDrug } from '../../interfaces';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import DOMPurify from 'dompurify';
import { marked } from 'marked';

@Component({
    selector: 'app-mydoc',
    templateUrl: './mydoc.component.html',
    styleUrls: ['./mydoc.component.scss'],
    standalone: false
})
export class MydocComponent {
    progressMessage = '';
    isLoading = false
    queryControl = new FormControl('');
    selectedThread = new FormControl('');
    threads: any[] = []; // This will hold the list of threads fetched from the API
    conversationHistory: any[] = []; // This will 11hold the conversation history for the selected thread
    currentBotMessage = '';
    finalAnalysis: any = null;
    interactionResults: InteractionResult[] = [];
    pseudoscienceFlags: PseudoscienceFlag[] = [];
    verifiedDrugs: VerifiedDrug[] = [];
    groupedSources: { type: string; links: SourceLink[] }[] = [];
    constructor(private apiService: APIService, private cdr: ChangeDetectorRef, private sanitizer: DomSanitizer) {
        this.fetchMe();
        this.selectedThread.valueChanges.subscribe(threadId => {
            if (threadId) {
                this.fetchThreadData(threadId);
            }
        });
    }

    fetchMe() {
        this.apiService.getData('/me').subscribe({
            next: (response) => {
                console.log('User info from API:', response);
                this.fetchThreads();

                // Handle the response as needed
            }, error: (error) => {
                console.error('Error fetching user info:', error);
            }
        });
    }

    fetchThreads() {
        this.apiService.getData('/threads').subscribe({
            next: (response) => {
                console.log('Threads from API:', response);
                this.threads = response; // Assuming the API returns an array of threads
                this.cdr.markForCheck(); // Trigger change detection to update the UI
            }, error: (error) => {
                console.error('Error fetching threads:', error);
            }
        });
    }

    fetchThreadData(threadId: string) {
        this.apiService.getData(`/thread/${threadId}`).subscribe({
            next: (response) => {
                console.log('Thread data from API:', response);
                this.conversationHistory = [];
                response.forEach((turn: any) => {
                    if (turn.role === 'user' || turn.role === 'assistant') {
                        turn.message = turn.role === 'user' ? turn.content : turn.content.query_response;
                        turn.message = this.getSafeHtml(turn.message);
                        this.conversationHistory.push(turn);
                    }
                    this.fetchAnalysisResults();
                });
                // Handle the response as needed
            }, error: (error) => {
                console.error('Error fetching thread data:', error);
            }
        });
    }

    sendMessage() {
        const query = this.queryControl.value;
        if (query) {
            this.queryControl.setValue(''); // Clear the input field
            let route = '/analyze'
            this.isLoading = true;
            this.conversationHistory.push({
                role: 'user',
                message: query,
                timestamp: new Date()
            });
            const payload:any = { query };
            if (this.selectedThread.value) {
                payload['thread_id'] = this.selectedThread.value;
                
            }
            this.apiService.streamPostData(route, payload).subscribe(
                {
                    next: (event: any) => {
                        if (!event || !event.type) return; // Ignore malformed events
                        if(event.thread_id) {
                            this.selectedThread.setValue(event.thread_id, { emitEvent: false }); // Update selected thread without triggering fetch
                        }
                        switch (event.type) {
                            case 'progress':
                                this.progressMessage = event.message;
                                break;


                            case 'chat_stream':
                                // Append tokens for the typewriter effect
                                this.currentBotMessage += event.token;
                                // this.currentBotMessage = this.getSafeHtml(this.currentBotMessage) as string; // Sanitize and convert to SafeHtml
                                break;

                            case 'done':
                                this.finalizeMessage();
                                break;
                        }
                        this.cdr.markForCheck(); // Trigger change detection to update the UI
                    },
                    error: (err) => {
                        console.error('Stream failed', err);
                        this.currentBotMessage = 'An error occurred during analysis.';
                        this.finalizeMessage();
                    },
                    complete: () => {
                        if (this.isLoading) this.finalizeMessage();
                    }
                });
        }
    }

    private finalizeMessage() {
        this.isLoading = false;
        if (this.currentBotMessage) {
            this.conversationHistory.push({
                role: 'assistant',
                message: this.getSafeHtml(this.currentBotMessage),
                timestamp: new Date()
            });
            this.currentBotMessage = '';
        }
        this.fetchAnalysisResults()
    }

    fetchAnalysisResults() {
        this.apiService.postData('/fetch-analysis', { thread_id: this.selectedThread.value }).subscribe({
            next: (response) => {
                console.log('Analysis results from API:', response);
                this.finalAnalysis = response;               
                this.interactionResults = this.finalAnalysis?.interaction_results || [];
                this.pseudoscienceFlags = this.finalAnalysis?.pseudoscience_flags || [];
                this.verifiedDrugs = this.finalAnalysis?.verified_drugs || [];
                this.groupedSources = this.buildGroupedSources(this.finalAnalysis?.all_sources || []);
                this.cdr.markForCheck();
            }
        });
    }

    private buildGroupedSources(sources: SourceLink[]): { type: string; links: SourceLink[] }[] {
        const seen = new Set<string>();
        const unique = sources.filter(s => {
            if (seen.has(s.url)) return false;
            seen.add(s.url);
            return true;
        });
        const order = ['pubmed', 'openfda', 'rxnorm', 'icd11'];
        const map = new Map<string, SourceLink[]>();
        for (const s of unique) {
            if (!map.has(s.type)) map.set(s.type, []);
            map.get(s.type)!.push(s);
        }
        return order
            .filter(t => map.has(t))
            .map(t => ({ type: t, links: map.get(t)! }));
    }

    getSafeHtml(markdownText: string): SafeHtml {
        const rawHtml = marked.parse(markdownText) as string;
        const cleanHtml = DOMPurify.sanitize(rawHtml);
        return this.sanitizer.bypassSecurityTrustHtml(cleanHtml);
    }

    startNewConversation() {
        this.selectedThread.setValue('');
        this.conversationHistory = [];
        this.finalAnalysis = null;
        this.interactionResults = [];
        this.pseudoscienceFlags = [];
        this.verifiedDrugs = [];
        this.groupedSources = [];
    }
}
