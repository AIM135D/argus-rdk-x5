import { AlertTriangle, CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";

interface Step {
  name: string;
  status: string;
  message?: string;
}

function icon(status: string) {
  if (status === "success") return <CheckCircle2 size={18} />;
  if (status === "warning") return <AlertTriangle size={18} />;
  if (status === "failed") return <XCircle size={18} />;
  if (status === "running") return <Loader2 size={18} className="spin" />;
  return <Circle size={18} />;
}

export default function ProgressSteps({ steps }: { steps: Step[] }) {
  return (
    <div className="progress-steps">
      {steps.map((step) => (
        <div className={`step ${step.status}`} key={step.name}>
          {icon(step.status)}
          <div>
            <div className="step-name">{step.name}</div>
            {step.message ? <div className="step-message">{step.message}</div> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
