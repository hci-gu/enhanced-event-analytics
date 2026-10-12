import type { AnalysisState } from './analysis'
import AnalysisScreen from './AnalysisScreen'
import SummaryScreen from './SummaryScreen'
import type { Page } from './navigation'

export default function AnalysisView({ analysis, text, page = analysis.status === 'completed' ? 'summary' : 'status', onNewAnalysis }: {
  analysis: AnalysisState; text: string; page?: Exclude<Page, 'home'>; onNewAnalysis?: () => void
}) {
  return page === 'summary' && analysis.status === 'completed'
    ? <SummaryScreen analysis={analysis} text={text} onNewAnalysis={onNewAnalysis} />
    : <AnalysisScreen analysis={analysis} />
}
