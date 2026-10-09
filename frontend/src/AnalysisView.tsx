import type { AnalysisState } from './analysis'
import AnalysisScreen from './AnalysisScreen'
import SummaryScreen from './SummaryScreen'

export default function AnalysisView({ analysis, text }: { analysis: AnalysisState; text: string }) {
  return analysis.status === 'completed'
    ? <SummaryScreen analysis={analysis} text={text} />
    : <AnalysisScreen analysis={analysis} />
}
