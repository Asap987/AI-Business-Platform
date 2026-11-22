import { redirect } from "next/navigation";

/** The Communication Center is a section, not a page: open its main view. */
export default function CommunicationPage() {
  redirect("/communication/conversations");
}
