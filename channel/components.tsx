/**
 * P3's fixed, policy-free UI registry for CopilotKit Channels.
 *
 * Every prop is JSON-serializable. These components only explain a Decision
 * made by Python; they never retrieve facts or choose an action.
 */

import {
  Context,
  Divider,
  Fields,
  Field,
  Header,
  Message,
  Section,
} from "@copilotkit/channels/ui";

export type AudienceMember = {
  id: string;
  name: string;
  avatarUrl: string;
};

export type DecisionAction = "allow" | "redact" | "broker";

export type AudienceCardProps = {
  sourceAudience: AudienceMember[];
  venueAudience: AudienceMember[];
  ownerName: string;
  status: string;
};

export type DisclosureDecisionProps = {
  action: DecisionAction;
  reason: string;
  answer?: string | null;
  redactedAnswer?: string | null;
  audience?: AudienceCardProps | null;
};

export type ConsentCardProps = {
  ownerName: string;
  question: string;
  factPreview: string;
  status: "pending" | "approved" | "denied" | "approved_with_constraint";
};

const MAX_CONTEXT_ELEMENTS = 10;
const MAX_AVATARS = MAX_CONTEXT_ELEMENTS - 1;

function unseenAudience(source: AudienceMember[], venue: AudienceMember[]): AudienceMember[] {
  const sourceIds = new Set(source.map((member) => member.id));
  return venue.filter((member) => !sourceIds.has(member.id));
}

function AvatarRow({ audience, label }: { audience: AudienceMember[]; label: string }) {
  const visible = audience.slice(0, MAX_AVATARS);
  const remainder = audience.length - visible.length;
  const countLabel = audience.length === 1 ? "person" : "people";

  return (
    <>
      <Section>{label + " · " + audience.length + " " + countLabel}</Section>
      {(visible.length > 0 || remainder > 0) && (
        <Context>
          {/* Slack Context blocks require non-empty text elements. Names are
              dependable across adapters; avatar images made Slack reject the
              entire decision card as invalid_blocks. */}
          {visible.map((member) => member.name || member.id)}
          {remainder > 0 ? "+" + remainder : null}
        </Context>
      )}
    </>
  );
}

/** Shows why a disclosure is being held, including both actual audiences. */
export function AudienceCard(props: AudienceCardProps) {
  const newlyExposed = unseenAudience(props.sourceAudience, props.venueAudience);
  const differenceLabel =
    newlyExposed.length === 1 ? "1 person was never part of this" : newlyExposed.length + " people were never part of this";

  return (
    <Message accent="#EAB308" fallbackText={"Disclosure held pending the fact owner's approval."}>
      <Header>🔒 Disclosure held</Header>
      <AvatarRow audience={props.sourceAudience} label="Could see the source" />
      <AvatarRow audience={props.venueAudience} label="Can see this channel" />
      <Fields>
        <Field label="Audience difference">{differenceLabel}</Field>
        <Field label="Fact owner">{props.ownerName}</Field>
      </Fields>
      <Divider />
      <Section>{"Holding it until " + props.ownerName + " decides."}</Section>
      <Context>{"● " + props.status.toUpperCase()}</Context>
    </Message>
  );
}

/**
 * Renders an already-typed policy result. It intentionally has no fallback
 * policy: an unknown action is rejected by TypeScript and the Python boundary.
 */
export function DisclosureDecision(props: DisclosureDecisionProps) {
  const hasHeldFact = props.action === "broker" && Boolean(props.audience?.ownerName);
  const body =
    props.action === "allow"
      ? props.answer
      : props.action === "redact"
        ? props.redactedAnswer
        : hasHeldFact
          ? "This disclosure needs the fact owner's approval."
          : props.reason;

  return (
    <>
      <Message
        accent={props.action === "broker" ? "#EAB308" : props.action === "allow" ? "#16A34A" : "#DC2626"}
        fallbackText={props.reason}
      >
        <Header>
          {props.action === "broker"
            ? hasHeldFact
              ? "🔐 Permission needed"
              : "🔎 No matching information"
            : props.action === "allow"
              ? "✅ Safe to share"
              : "🔒 Disclosure held"}
        </Header>
        <Section>{body ?? props.reason}</Section>
        <Context>{props.reason}</Context>
        {props.action === "allow" ? (
          <>
            <Fields>
              <Field label="Status">Verified for this audience</Field>
              <Field label="Scope">Current channel</Field>
            </Fields>
          </>
        ) : null}
      </Message>
      {props.action === "broker" && props.audience ? <AudienceCard {...props.audience} /> : null}
    </>
  );
}

/**
 * The registered owner-facing presentation component. Phase 1's actual DM is
 * posted by P1 through WebClient because it is out-of-band from the Channel;
 * this component remains display-only until that callback route is verified.
 */
export function ConsentCard(props: ConsentCardProps) {
  return (
    <Message>
      <Header>{"Permission request for " + props.ownerName}</Header>
      <Section>{props.question}</Section>
      <Divider />
      <Section>{props.factPreview}</Section>
      <Context>{"Status: " + props.status}</Context>
    </Message>
  );
}

/** The only components P2 may register with the Channel runner. */
export const POLICY_COMPONENTS = [AudienceCard, DisclosureDecision, ConsentCard];
