/** Decorative school-brand artwork on a fixed canvas, independent of content height. */
export function HomepageBackground() {
  return (
    <div className="landing-background-art" aria-hidden="true">
      <svg
        className="landing-background-canvas"
        viewBox="0 0 1440 3000"
        preserveAspectRatio="none"
        focusable="false"
      >
        <g className="landing-background-field--rose">
          <path d="M780-80C1040 25 1090 165 1510 70V410C1220 390 1100 240 920 270 750 300 670 125 780-80Z" />
          <path d="M-100 620C220 540 300 980 660 950 900 930 1030 770 1510 910V1050C1050 950 930 1180 630 1090 240 970 190 740-100 840Z" />
          <path d="M-60 1840C210 1670 480 2010 800 1940S1200 1750 1510 1850V2020C1150 1870 1030 2200 750 2110 420 2020 230 1890-60 2030Z" />
        </g>
        <g className="landing-background-field--maroon">
          <path d="M-120 1390C230 1170 510 1460 770 1350 950 1270 1270 1140 1510 1320V1480C1220 1350 1060 1520 790 1510 430 1500 240 1370-120 1540Z" />
          <path d="M950 2260C1130 2130 1320 2420 1500 2350V2810C1280 2720 1250 2560 1100 2540 870 2510 790 2410 950 2260Z" />
          <path d="M-100 2910C290 2700 700 3050 1010 2850 1200 2730 1330 2750 1510 2880V3800H-100Z" />
        </g>
        <g className="landing-background-contours">
          <path d="M720-20C950 210 1190 110 1500 340" />
          <path d="M-80 785C270 650 300 1100 680 1040S1100 850 1510 1000" />
          <path d="M-80 1330C300 1140 500 1400 790 1290S1240 1110 1510 1260" />
          <path d="M-80 1990C270 1780 430 2160 790 2040S1180 1840 1510 1980" />
          <path d="M-80 2840C330 2670 650 2960 990 2780S1320 2670 1510 2810" />
        </g>
        <g className="landing-background-accents">
          <path d="M190 1798C260 1750 340 1770 390 1810 310 1780 250 1825 190 1798Z" />
          <path d="M1060 2916C1110 2870 1190 2880 1240 2920 1170 2895 1120 2945 1060 2916Z" />
        </g>
      </svg>
    </div>
  )
}
