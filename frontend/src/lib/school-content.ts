/**
 * His Care Christian Institute — public-facing school copy.
 *
 * Every string here is verbatim from the school's design file (CAPSTONE-UI,
 * nodes 688:10 Mission, 688:12 Vision, 688:32 About) or from the supplied
 * landing-page reference. Nothing is paraphrased or invented; edits belong in
 * the source design, not here.
 *
 * The Figma API returns U+2028 (line separator) for the designer's hard
 * breaks: intentional paragraph breaks before the numbered Mission items are
 * kept as real newlines (render with `whitespace-pre-line`), while the
 * designer's mid-sentence re-wraps in the About text are joined back into
 * flowing prose to match how the school's own poster renders it (the one
 * "K- 008" join is the recognition number the wrap split).
 */

export const SCHOOL_NAME = "HIS CARE CHRISTIAN INSTITUTE"
export const SCHOOL_CAMPUS_LINE = "of Santa Maria, Sto. Tomas Batangas Inc."

/** First paragraph of the About text — the landing excerpt. */
export const ABOUT_EXCERPT =
  "Leila D. Paragoso and Clemente T. Paragoso both in their 60's founded " +
  "His Care Christian Institute in April 2007. His Care meaning God's Care " +
  "all started at Blk 2 Lot 53, Ramonita Homes, Darasa, Tanauan City, " +
  "Batangas. Considering the needs of children with parents who are not " +
  "capable of sending their children to a private schools due to high " +
  "tuition fees, the founder decided to put up a Preschool class (children " +
  "with ages 3 to 5 years old.)"

/** Full About the School text (node 688:32). */
export const ABOUT_TEXT =
  "Leila D. Paragoso and Clemente T. Paragoso both in their 60's founded " +
  "His Care Christian Institute in April 2007. His Care meaning God's Care " +
  "all started at Blk 2 Lot 53, Ramonita Homes, Darasa, Tanauan City, " +
  "Batangas. Considering the needs of children with parents who are not " +
  "capable of sending their children to a private schools due to high " +
  "tuition fees, the founder decided to put up a Preschool class (children " +
  "with ages 3 to 5 years old.) On their 1st year they started having 30 " +
  "students dividing it into 3 sessions. By the grace of God, hard work and " +
  "passion, after 3 years they have expanded their school His Care " +
  "Christian Institute is fully accredited, non-sectarian, co-educational " +
  "with 3 campuses namely His Care Christian Institute Darasa, Tanauan, " +
  "Batangas Inc located at 1167 Darasa ,Tanauan City, Batangas having " +
  "Nursery, Kindergarten through Grade Ten with DepEd Permit NKP- Gov. " +
  "Recognition K-008 S. 2012, Elem- Gov. Permit NO. E-180, S.2021, " +
  "Secondary- Gov. Recognition NO. S-123 S. 2017 under K to 12 Curriculum. " +
  "His Care Christian Institute of Tanauan, Batangas Inc located at Zone " +
  "IV, Bagumbayan, Tanauan City, Batangas having Nursery, Kindergarten " +
  "through Grade Ten with DepEd Government Recognition Nos. K- 053 S. " +
  "2017, E-054, S.2007, and S-144 S. 2018 under K to 12 Curriculum and " +
  "MATATAG Curiculum. His Care Christian Institute of Santa Maria, Sto. " +
  "Tomas, Batangas Inc located at Sec 8 Blue Isle Subd., Sta. Maria, Sto. " +
  "Tomas, Batangas."

/** Full Mission text (node 688:10) — newlines are the design's hard breaks. */
export const MISSION_TEXT = `His Care Christian Institute (HCCI) is dedicated in providing quality basic education where:
1. Biblical memory verse are injected and incorporated as guide in training up the students.
2. The administration, teachers and staff are committed in enhancing the unique learning styles of our students in a DISCOVERING, CHALLENGING AND TRANSFORMING environment in order to become an exceptional member of our diverse global community that will lead them to their God-given purpose.
3. Together we produce students with excellent academic abilities and strong Christian Values, ready to serve the Home, the School and the Community.`

/** Full Vision text (node 688:12). */
export const VISION_TEXT =
  "As a Christian Educational Institution, we envision ourselves to " +
  "build and produce a community of intellectuals, through quality " +
  "educators who will bring into play the uplifting of the Christian " +
  "core values in the classroom's daily activities. We are committed in " +
  "transforming students in becoming lifelong learners, in fulfillment " +
  "of a God-given purpose."

/**
 * Contact details — DRAFT, taken from the supplied banner reference
 * (school ID, address, e-mail as printed there). The phone number is
 * deliberately absent: no real number has been provided, and inventing one
 * would ship false contact data.
 */
export const CONTACT = {
  address:
    "Sec. 8 Blue Isle Subd., Barangay Santa Maria, Sto. Tomas, Batangas, Inc.",
  schoolId: "423566",
  email: "hiscarestamariaregistrar@gmail.com",
} as const
