import { createBrowserRouter } from "react-router-dom"

import { appRoutes } from "@/routes/routes"

/** Browser router (library mode) over the PH11.3 route table. */
export const router = createBrowserRouter(appRoutes)
