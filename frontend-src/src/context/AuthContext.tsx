import React, { createContext, useContext, useState, useEffect } from "react";

export interface DoctorUser {
  clinician_id: string;
  clinician_role: string;
  display_name: string;
  authorized_override: boolean;
}

interface AuthContextType {
  token: string | null;
  doctor: DoctorUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (doctorId: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("microbe_token"));
  const [doctor, setDoctor] = useState<DoctorUser | null>(() => {
    const saved = localStorage.getItem("microbe_doctor");
    return saved ? JSON.parse(saved) : null;
  });
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const verifyToken = async () => {
      const savedToken = localStorage.getItem("microbe_token");
      if (!savedToken) {
        setIsLoading(false);
        return;
      }

      try {
        const res = await fetch("/api/auth/me", {
          headers: {
            Authorization: `Bearer ${savedToken}`,
          },
        });

        if (res.ok) {
          const data = await res.json();
          const docData: DoctorUser = {
            clinician_id: data.clinician_id,
            clinician_role: data.clinician_role,
            display_name: data.display_name || data.clinician_id,
            authorized_override: !!data.authorized_override,
          };
          setDoctor(docData);
          localStorage.setItem("microbe_doctor", JSON.stringify(docData));
        } else {
          // Token invalid or expired
          logout();
        }
      } catch (err) {
        console.error("Failed to verify authentication token:", err);
      } finally {
        setIsLoading(false);
      }
    };

    verifyToken();
  }, []);

  const login = async (doctorId: string, password: string) => {
    try {
      const res = await fetch("/api/auth/token", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: doctorId.trim(),
          password: password,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        return {
          success: false,
          error: data.detail || "Authentication failed. Invalid Doctor ID or password.",
        };
      }

      const docData: DoctorUser = {
        clinician_id: data.clinician_id,
        clinician_role: data.clinician_role,
        display_name: data.display_name || data.clinician_id,
        authorized_override: !!data.authorized_override,
      };

      setToken(data.access_token);
      setDoctor(docData);

      localStorage.setItem("microbe_token", data.access_token);
      localStorage.setItem("microbe_doctor", JSON.stringify(docData));

      return { success: true };
    } catch (err: any) {
      return {
        success: false,
        error: err.message || "Network error while logging in.",
      };
    }
  };

  const logout = () => {
    setToken(null);
    setDoctor(null);
    localStorage.removeItem("microbe_token");
    localStorage.removeItem("microbe_doctor");
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        doctor,
        isAuthenticated: !!token && !!doctor,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
