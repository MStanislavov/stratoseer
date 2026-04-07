import {
  UserPlus,
  Play,
  Search,
  FileText,
  Shield,
  ArrowRight,
} from "lucide-react"
import { Link } from "react-router-dom"
import { PageHeader } from "@/components/shared/PageHeader"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface StepProps {
  number: number
  title: string
  description: string
  icon: React.ReactNode
  details: string[]
  link?: { label: string; to: string }
}

function StepCard({ number, title, description, icon, details, link }: StepProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">
            {number}
          </div>
          <div className="flex items-center gap-2">
            {icon}
            <CardTitle className="text-lg">{title}</CardTitle>
          </div>
        </div>
        <CardDescription className="ml-11">{description}</CardDescription>
      </CardHeader>
      <CardContent className="ml-11">
        <ul className="space-y-2 text-sm text-muted-foreground">
          {details.map((detail) => (
            <li key={detail} className="flex items-start gap-2">
              <ArrowRight className="h-4 w-4 mt-0.5 shrink-0 text-primary" />
              <span>{detail}</span>
            </li>
          ))}
        </ul>
        {link && (
          <Link
            to={link.to}
            className="inline-flex items-center gap-1 mt-4 text-sm font-medium text-primary hover:underline"
          >
            {link.label}
            <ArrowRight className="h-3 w-3" />
          </Link>
        )}
      </CardContent>
    </Card>
  )
}

const steps: StepProps[] = [
  {
    number: 1,
    title: "Create a Profile",
    description:
      "Profiles are independent workspaces that represent different career personas or job search strategies. Each profile needs a few essentials before you can run scouts.",
    icon: <UserPlus className="h-5 w-5 text-primary" />,
    details: [
      "Go to the Dashboard and click \"New Profile\".",
      "Give it a name that reflects this persona (e.g. \"Backend Engineer\", \"Architect\").",
      "Upload your CV (PDF supported) -- this is required so agents can match opportunities to your background and extract skills automatically.",
      "Add at least one career goal describing what you want to achieve (e.g. \"Find a senior backend role\", \"Earn an AWS certification\").",
      "Add your skills so scouts know what to search for and the verifier can score relevance.",
      "Add your preferred job titles so scouts know exactly what roles to search for on LinkedIn (e.g. \"Staff Engineer\", \"Engineering Manager\").",
      "Optionally refine your profile with industries, locations, work arrangement, and learning preferences.",
    ],
    link: { label: "Go to Dashboard", to: "/" },
  },
  {
    number: 2,
    title: "Start a Run",
    description:
      "Runs are automated intelligence-gathering sessions powered by scout agents.",
    icon: <Play className="h-5 w-5 text-primary" />,
    details: [
      "Open your profile and navigate to \"Runs\".",
      "Click \"Start Run\" and choose a mode: Daily (job postings), Weekly (trends and certifications), or Cover Letter.",
      "The system dispatches scout agents to search for relevant opportunities based on your profile targets.",
      "Watch progress in real-time via the SSE stream as each agent completes its work.",
    ],
  },
  {
    number: 3,
    title: "Review Results",
    description:
      "Browse the opportunities, trends, and certifications discovered by your agents.",
    icon: <Search className="h-5 w-5 text-primary" />,
    details: [
      "Go to \"Results\" under your profile to see discovered opportunities.",
      "Filter results by run to compare across sessions.",
      "Each result includes evidence links and confidence scores validated by the verifier.",
      "Weekly runs additionally surface industry trends and relevant certifications.",
    ],
  },
  {
    number: 4,
    title: "Generate Cover Letters",
    description:
      "Create tailored cover letters for specific opportunities using your CV and the job details.",
    icon: <FileText className="h-5 w-5 text-primary" />,
    details: [
      "Navigate to \"Cover Letters\" under your profile.",
      "Select an opportunity and click \"Generate\".",
      "The cover letter agent uses your CV, the job description, and extracted requirements.",
      "Review, edit, and download the generated letter.",
    ],
  },
  {
    number: 5,
    title: "Understand Policies",
    description:
      "Policies govern what agents can and cannot do. They are read-only and version-controlled.",
    icon: <Shield className="h-5 w-5 text-primary" />,
    details: [
      "Visit the Policies page to see all active YAML policy files.",
      "Policies control tool allowlists, token budgets, data boundaries, and PII redaction rules.",
      "The verifier agent enforces these policies on every run, rejecting non-compliant outputs.",
      "To change policies, edit the YAML files in the /policy directory and commit via git.",
    ],
    link: { label: "View Policies", to: "/policies" },
  },
]

export default function GuidePage() {
  return (
    <div>
      <PageHeader
        title="Guide"
        description="Learn how to use Stratoseer to power your career intelligence"
      />

      <div className="space-y-4">
        {steps.map((step) => (
          <StepCard key={step.number} {...step} />
        ))}
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Tips</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li className="flex items-start gap-2">
              <ArrowRight className="h-4 w-4 mt-0.5 shrink-0 text-primary" />
              <span>
                Create multiple profiles for different job search strategies and compare results across them.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <ArrowRight className="h-4 w-4 mt-0.5 shrink-0 text-primary" />
              <span>
                Run daily scouts frequently to catch new postings early. Weekly runs are best for tracking broader trends.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <ArrowRight className="h-4 w-4 mt-0.5 shrink-0 text-primary" />
              <span>
                Use the replay feature on past runs to detect drift in job postings or trend data over time.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <ArrowRight className="h-4 w-4 mt-0.5 shrink-0 text-primary" />
              <span>
                Every claim in results is backed by evidence with URL and content hash, so you can verify sources directly.
              </span>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
