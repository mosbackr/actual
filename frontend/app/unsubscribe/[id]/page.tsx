"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export default function UnsubscribePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const investorId = params.id as string;
  const token = searchParams.get("token") || "";

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!investorId || !token) {
      setStatus("error");
      setErrorMsg("Invalid unsubscribe link.");
      return;
    }

    fetch(`${API_URL}/api/unsubscribe/${investorId}?token=${encodeURIComponent(token)}`, {
      method: "POST",
    })
      .then((res) => {
        if (res.ok) {
          setStatus("success");
        } else {
          setStatus("error");
          setErrorMsg("This unsubscribe link is invalid or has expired.");
        }
      })
      .catch(() => {
        setStatus("error");
        setErrorMsg("Something went wrong. Please try again later.");
      });
  }, [investorId, token]);

  return (
    <div className="min-h-screen bg-[#FAFAF8] flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center">
        {/* Logo */}
        <div className="mb-8">
          <span
            className="inline-flex items-center justify-center w-10 h-10 rounded-full text-white font-bold text-lg"
            style={{ backgroundColor: "#F28C28" }}
          >
            D
          </span>
          <span className="ml-2 text-xl font-bold text-[#1A1A1A] align-middle">
            Deep Thesis
          </span>
        </div>

        {status === "loading" && (
          <p className="text-[#6B6B6B] text-sm">Processing your request...</p>
        )}

        {status === "success" && (
          <>
            <h1 className="text-2xl font-semibold text-[#1A1A1A] mb-3">
              You&apos;ve been unsubscribed
            </h1>
            <p className="text-[#6B6B6B] text-sm">
              You will no longer receive marketing emails from Deep Thesis.
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <h1 className="text-2xl font-semibold text-[#1A1A1A] mb-3">
              Something went wrong
            </h1>
            <p className="text-[#6B6B6B] text-sm">{errorMsg}</p>
          </>
        )}
      </div>
    </div>
  );
}
