import { Link } from "react-router-dom"

import "./public-school.css"

export function PublicFooter() {
  return (
    <footer className="public-school-footer">
      <div className="public-school-footer-inner">
        <p className="public-school-footer-copyright">
          © {new Date().getFullYear()} His Care Christian Institute. All rights
          reserved.
        </p>
        <nav
          aria-label="Footer navigation"
          className="public-school-footer-nav"
        >
          <Link to="/school">About the school</Link>
          <a href="/#announcements">Announcements</a>
          <a href="/#resources">Resources</a>
          <a href="/#faq">FAQ</a>
          <a href="/#contact">Contact</a>
        </nav>
        <nav aria-label="Legal links" className="public-school-footer-policies">
          <Link to="/privacy">Privacy Policy</Link>
          <Link to="/terms">Terms of Use</Link>
          <Link to="/cookies">Cookie Policy</Link>
        </nav>
      </div>
    </footer>
  )
}
