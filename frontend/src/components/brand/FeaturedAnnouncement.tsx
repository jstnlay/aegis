import { Crown, MessageCircle } from "lucide-react"

/** School-supplied event feature, independent of the live CMS feed. */
export function FeaturedAnnouncement() {
  return (
    <article className="landing-event" aria-labelledby="landing-event-title">
      <div className="landing-event-media">
        <a
          href="/announcement%20pic.png"
          target="_blank"
          rel="noopener noreferrer"
          className="landing-event-poster"
          aria-label="View the full Mister & Miss HIS CARE 2027 poster"
        >
          <img
            src="/announcement%20pic.png"
            alt="Mister & Miss HIS CARE 2027 event poster with a gold crown and silhouettes on a green background"
            width={899}
            height={506}
            loading="lazy"
            decoding="async"
          />
        </a>
        <p className="landing-event-closing">
          Let us support and celebrate our learners as they take the spotlight!{" "}
          <span aria-hidden="true">👑 ✨</span>
        </p>
      </div>
      <div className="landing-event-copy">
        <span className="landing-event-label">
          <Crown aria-hidden="true" className="size-4" /> School event
        </span>
        <h3 id="landing-event-title">Mister &amp; Miss HIS CARE 2027!</h3>
        <p>
          <strong>The search is on!</strong> Get ready to witness confidence,
          talent, intelligence, and grace as we celebrate the candidates of
          Mister &amp; Miss HIS CARE 2027!
        </p>
        <p>
          This is an opportunity for our learners to showcase their unique
          qualities, build confidence, and create unforgettable memories as part
          of the HIS CARE family.
        </p>
        <div className="landing-event-inquiry">
          <MessageCircle aria-hidden="true" className="size-5" />
          <p>
            For more details and inquiries, kindly look for{" "}
            <strong>Ms. Anica Elain R. Banquil</strong> or coordinate with your
            child&apos;s <strong>Class Adviser.</strong>
          </p>
        </div>
      </div>
    </article>
  )
}
